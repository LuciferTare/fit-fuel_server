import json
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from music.models import Playlist, PlaylistSong, Song

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "seed_data"

# Playlists whose media no longer ships inside the Flutter bundle: they are served
# from MEDIA_ROOT as absolute URLs and downloaded on demand by the app.
DEFAULT_REMOTE_PLAYLISTS = "4,5,6,7,8,9"

# MEDIA_ROOT-relative destinations, mirroring each field's ``upload_to``.
AUDIO_DIR = "music/audio"
THUMB_DIR = "music/thumbs"
ICON_DIR = "music/icons"
COVER_DIR = "music/covers"


def safe_name(name):
    """Storage-safe filename, matching what Django would keep on a real upload."""
    return re.sub(r"[^-\w.]", "", name.replace("&", "and").replace(" ", "_"))


class Command(BaseCommand):
    help = (
        "Seed the bundled songs.json / playlists.json into the DB so backend ids "
        "continue from the bundled sequence (168 / 10). Playlists named by "
        f"--remote-playlists (default {DEFAULT_REMOTE_PLAYLISTS}) are seeded as "
        "remote: their media is copied into MEDIA_ROOT and served as absolute URLs. "
        "Every other playlist stays bundled, keeping its 'assets/...' paths. "
        "Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--songs",
            default=str(DEFAULT_DIR / "songs.json"),
            help="Path to the bundled songs.json export.",
        )
        parser.add_argument(
            "--playlists",
            default=str(DEFAULT_DIR / "playlists.json"),
            help="Path to the bundled playlists.json export.",
        )
        parser.add_argument(
            "--remote-playlists",
            default=DEFAULT_REMOTE_PLAYLISTS,
            help=(
                "Comma-separated playlist ids to seed as remote "
                f"(default {DEFAULT_REMOTE_PLAYLISTS}). Pass an empty string to seed "
                "everything as bundled."
            ),
        )
        parser.add_argument(
            "--app-root",
            default=None,
            help=(
                "Flutter project root (e.g. D:\\Flutter\\FitandFuel), used to resolve "
                "the 'assets/...' paths when copying remote media into MEDIA_ROOT. "
                "Only needed the first time — once the media is in MEDIA_ROOT it is "
                "reused as-is."
            ),
        )

    def _load(self, path):
        p = Path(path)
        if not p.exists():
            raise CommandError(f"File not found: {p}")
        with p.open(encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _parse_ids(raw):
        try:
            return {int(part) for part in str(raw).replace(",", " ").split()}
        except ValueError:
            raise CommandError(f"--remote-playlists must be integer ids, got: {raw!r}")

    def _place(self, ref, subdir):
        """Copy a bundled asset ref into MEDIA_ROOT; return its stored relative name."""
        if not ref:
            return None
        rel = f"{subdir}/{safe_name(Path(ref).name)}"
        dest = Path(settings.MEDIA_ROOT) / rel
        if dest.exists():
            self.reused += 1
            return rel
        if self.app_root is None:
            self._warn(f"{ref}: absent from MEDIA_ROOT — pass --app-root to copy it")
            return None
        src = self.app_root / ref
        if not src.is_file():
            self._warn(f"{ref}: not found under {self.app_root}")
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        self.copied += 1
        return rel

    def _warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    @transaction.atomic
    def handle(self, *args, **options):
        songs = self._load(options["songs"])
        playlists = self._load(options["playlists"])
        remote_playlist_ids = self._parse_ids(options["remote_playlists"])

        self.app_root = Path(options["app_root"]) if options["app_root"] else None
        if self.app_root is not None and not self.app_root.is_dir():
            raise CommandError(f"--app-root is not a directory: {self.app_root}")

        unknown = sorted(remote_playlist_ids - {row["id"] for row in playlists})
        if unknown:
            raise CommandError(f"--remote-playlists names unknown playlist ids: {unknown}")

        # A song is only remote when every playlist holding it is remote, so a song
        # shared with a bundled playlist keeps its offline asset paths.
        remote_song_ids, bundled_song_ids = set(), set()
        for row in playlists:
            holder = (
                remote_song_ids
                if row["id"] in remote_playlist_ids
                else bundled_song_ids
            )
            holder.update(row.get("song_ids", []))
        remote_song_ids -= bundled_song_ids

        self.copied = 0
        self.reused = 0
        self.warnings = []

        for row in songs:
            is_remote = row["id"] in remote_song_ids
            Song.objects.update_or_create(
                id=row["id"],
                defaults={
                    "title": row.get("title") or "",
                    "artist": row.get("artist") or "",
                    "duration": row.get("duration") or 0,
                    "thumb_file": (
                        self._place(row.get("thumb"), THUMB_DIR) if is_remote else None
                    ),
                    "asset_file": (
                        self._place(row.get("asset"), AUDIO_DIR) if is_remote else None
                    ),
                    "thumb_ref": None if is_remote else row.get("thumb"),
                    "asset_ref": None if is_remote else row.get("asset"),
                    "is_remote": is_remote,
                },
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(songs)} songs "
                f"({len(remote_song_ids)} remote, {len(songs) - len(remote_song_ids)} bundled)."
            )
        )

        for row in playlists:
            is_remote = row["id"] in remote_playlist_ids
            playlist, _ = Playlist.objects.update_or_create(
                id=row["id"],
                defaults={
                    "title": row.get("title") or "",
                    "color": row.get("color") or "",
                    "icon_file": (
                        self._place(row.get("icon"), ICON_DIR) if is_remote else None
                    ),
                    "cover_file": (
                        self._place(row.get("cover"), COVER_DIR) if is_remote else None
                    ),
                    "icon_ref": None if is_remote else row.get("icon"),
                    "cover_ref": None if is_remote else row.get("cover"),
                    "is_remote": is_remote,
                },
            )
            playlist.playlist_songs.all().delete()
            PlaylistSong.objects.bulk_create(
                [
                    PlaylistSong(playlist=playlist, song_id=sid, position=index)
                    for index, sid in enumerate(row.get("song_ids", []))
                ]
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(playlists)} playlists "
                f"({len(remote_playlist_ids)} remote, "
                f"{len(playlists) - len(remote_playlist_ids)} bundled)."
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Remote media: {self.copied} copied into MEDIA_ROOT, "
                f"{self.reused} already present."
            )
        )
        for message in self.warnings:
            self.stdout.write(self.style.WARNING(f"  no media for {message}"))

        next_song = (Song.objects.order_by("-id").values_list("id", flat=True).first() or 0) + 1
        next_playlist = (Playlist.objects.order_by("-id").values_list("id", flat=True).first() or 0) + 1

        # Make "next id continues the bundled sequence" unconditional rather than an
        # implicit side effect of how each row got inserted, so a song/playlist
        # created afterwards (e.g. from the app) can never collide with a seeded id.
        # MySQL ignores an AUTO_INCREMENT value that isn't above the current counter,
        # so this is always safe to re-run.
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {Song._meta.db_table} AUTO_INCREMENT = {next_song}"
            )
            cursor.execute(
                f"ALTER TABLE {Playlist._meta.db_table} AUTO_INCREMENT = {next_playlist}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Next song id: {next_song} | Next playlist id: {next_playlist}"
            )
        )
