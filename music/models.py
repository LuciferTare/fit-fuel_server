from django.conf import settings
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class MusicBaseModel(models.Model):
    """Audit + soft-delete fields, mirroring ``core.models.BaseModel``.

    Note: unlike the rest of the project, music models use an integer
    ``BigAutoField`` primary key instead of a UUID. The id is a contract with
    the Flutter app's bundled ``songs.json`` / ``playlists.json`` (integer ids
    ``1..138`` / ``1..7``); backend-created rows must continue that sequence so
    the offline bundle and online catalogue never collide.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
        editable=False,
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    active_objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def soft_delete(self, deleted_by=None):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class Song(MusicBaseModel):
    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=255)
    artist = models.CharField(max_length=255, blank=True)
    duration = models.PositiveIntegerField(default=0, help_text="Length in seconds")

    # Remote uploads — populated only for admin-added (is_remote) songs.
    thumb_file = models.ImageField(upload_to="music/thumbs/", null=True, blank=True)
    asset_file = models.FileField(
        upload_to="music/audio/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(["opus"])],
    )

    # Bundled asset paths — the literal ``assets/...`` strings for seeded rows.
    # Nullable: some bundled songs have no thumbnail (app falls back to a default).
    thumb_ref = models.CharField(max_length=500, null=True, blank=True)
    asset_ref = models.CharField(max_length=500, null=True, blank=True)

    is_remote = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "songs"
        ordering = ["id"]

    def __str__(self):
        return f"{self.id} — {self.title}"

    def soft_delete(self, deleted_by=None):
        super().soft_delete(deleted_by=deleted_by)
        # A deleted song has no business staying in anyone's playlist —
        # sever the join rows rather than leaving a dangling reference that
        # get_song_ids would otherwise keep returning.
        self.playlistsong_set.all().delete()


class Playlist(MusicBaseModel):
    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=255)
    color = models.CharField(
        max_length=8,
        blank=True,
        validators=[RegexValidator(r"^[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")],
        help_text="Hex color without '#', e.g. 520102",
    )

    # Remote uploads — populated only for admin-added (is_remote) playlists.
    icon_file = models.ImageField(upload_to="music/icons/", null=True, blank=True)
    cover_file = models.ImageField(upload_to="music/covers/", null=True, blank=True)

    # Bundled asset paths — the literal ``assets/...`` strings for seeded rows.
    # Nullable: a bundled playlist may lack an icon/cover (app falls back to a default).
    icon_ref = models.CharField(max_length=500, null=True, blank=True)
    cover_ref = models.CharField(max_length=500, null=True, blank=True)

    songs = models.ManyToManyField(
        Song, through="PlaylistSong", related_name="playlists"
    )

    is_remote = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "playlists"
        ordering = ["id"]

    def __str__(self):
        return f"{self.id} — {self.title}"


class PlaylistSong(models.Model):
    """Through model preserving the order of a playlist's ``song_ids``."""

    playlist = models.ForeignKey(
        Playlist, related_name="playlist_songs", on_delete=models.CASCADE
    )
    song = models.ForeignKey(Song, on_delete=models.CASCADE)
    position = models.PositiveIntegerField()

    class Meta:
        db_table = "playlist_songs"
        ordering = ["position"]
        unique_together = ("playlist", "song")

    def __str__(self):
        return f"{self.playlist_id}[{self.position}] -> {self.song_id}"
