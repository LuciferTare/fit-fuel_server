import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from music.models import Playlist, PlaylistSong, Song

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "seed_data"


class Command(BaseCommand):
    help = (
        "Seed the bundled songs.json / playlists.json into the DB so backend "
        "ids continue from the bundled sequence (139 / 8). Idempotent."
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

    def _load(self, path):
        p = Path(path)
        if not p.exists():
            raise CommandError(f"File not found: {p}")
        with p.open(encoding="utf-8") as fh:
            return json.load(fh)

    @transaction.atomic
    def handle(self, *args, **options):
        songs = self._load(options["songs"])
        playlists = self._load(options["playlists"])

        for row in songs:
            Song.objects.update_or_create(
                id=row["id"],
                defaults={
                    "title": row.get("title") or "",
                    "artist": row.get("artist") or "",
                    "duration": row.get("duration") or 0,
                    "thumb_ref": row.get("thumb"),
                    "asset_ref": row.get("asset"),
                    "is_remote": False,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(songs)} songs."))

        for row in playlists:
            playlist, _ = Playlist.objects.update_or_create(
                id=row["id"],
                defaults={
                    "title": row.get("title") or "",
                    "color": row.get("color") or "",
                    "icon_ref": row.get("icon"),
                    "cover_ref": row.get("cover"),
                    "is_remote": False,
                },
            )
            playlist.playlist_songs.all().delete()
            PlaylistSong.objects.bulk_create(
                [
                    PlaylistSong(playlist=playlist, song_id=sid, position=index)
                    for index, sid in enumerate(row.get("song_ids", []))
                ]
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(playlists)} playlists."))

        next_song = (Song.objects.order_by("-id").values_list("id", flat=True).first() or 0) + 1
        next_playlist = (Playlist.objects.order_by("-id").values_list("id", flat=True).first() or 0) + 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Next song id: {next_song} | Next playlist id: {next_playlist}"
            )
        )
