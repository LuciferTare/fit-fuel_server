from rest_framework import serializers

from core.serializers import UploadedFileURLField
from music.models import Playlist, PlaylistSong, Song


def _validate_opus(val):
    name = getattr(val, "name", "") or ""
    if not name.lower().endswith(".opus"):
        raise serializers.ValidationError("Audio must be a .opus file.")
    return val


class MediaRefMixin:
    """Resolve a media field to an absolute URL (remote uploads) or the
    bundled ``assets/...`` path string (seeded rows)."""

    def _resolve(self, file_field, ref):
        if file_field:
            request = self.context.get("request")
            url = file_field.url
            return request.build_absolute_uri(url) if request else url
        # Empty bundled ref → null, matching the app's source JSON (e.g. a song
        # with no thumbnail).
        return ref or None


# ── Songs ─────────────────────────────────────────────────────────────────────

class SongSerializer(MediaRefMixin, serializers.ModelSerializer):
    """Read shape — matches the app's ``songs.json`` plus ``is_remote``."""

    thumb = serializers.SerializerMethodField()
    asset = serializers.SerializerMethodField()

    class Meta:
        model = Song
        fields = ["id", "title", "artist", "thumb", "asset", "duration", "is_remote"]

    def get_thumb(self, obj):
        return self._resolve(obj.thumb_file, obj.thumb_ref)

    def get_asset(self, obj):
        return self._resolve(obj.asset_file, obj.asset_ref)


class SongCreateSerializer(serializers.ModelSerializer):
    """Write shape (multipart) for admin-added songs."""

    thumb = UploadedFileURLField(source="thumb_file", required=True)
    asset = serializers.FileField(source="asset_file", validators=[_validate_opus])

    class Meta:
        model = Song
        fields = ["title", "artist", "duration", "thumb", "asset"]

    def create(self, validated_data):
        validated_data["is_remote"] = True
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


# ── Playlists ───────────────────────────────────────────────────────────────

class PlaylistSerializer(MediaRefMixin, serializers.ModelSerializer):
    """Read shape — matches the app's ``playlists.json`` plus ``is_remote``."""

    icon = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()
    song_ids = serializers.SerializerMethodField()

    class Meta:
        model = Playlist
        fields = ["id", "title", "icon", "cover", "color", "song_ids", "is_remote"]

    def get_icon(self, obj):
        return self._resolve(obj.icon_file, obj.icon_ref)

    def get_cover(self, obj):
        return self._resolve(obj.cover_file, obj.cover_ref)

    def get_song_ids(self, obj):
        return list(
            obj.playlist_songs.order_by("position").values_list("song_id", flat=True)
        )


class PlaylistCreateSerializer(serializers.ModelSerializer):
    """Write shape (multipart) for admin-added playlists."""

    icon = UploadedFileURLField(source="icon_file", required=True)
    cover = UploadedFileURLField(source="cover_file", required=True)
    song_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, required=False
    )

    class Meta:
        model = Playlist
        fields = ["title", "icon", "cover", "color", "song_ids"]

    def validate_song_ids(self, value):
        existing = set(
            Song.active_objects.filter(id__in=value).values_list("id", flat=True)
        )
        missing = [sid for sid in value if sid not in existing]
        if missing:
            raise serializers.ValidationError(f"Unknown song ids: {missing}")
        return value

    def create(self, validated_data):
        song_ids = validated_data.pop("song_ids", [])
        validated_data["is_remote"] = True
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        playlist = super().create(validated_data)
        self._set_songs(playlist, song_ids)
        return playlist

    def update(self, instance, validated_data):
        song_ids = validated_data.pop("song_ids", None)
        playlist = super().update(instance, validated_data)
        if song_ids is not None:
            playlist.playlist_songs.all().delete()
            self._set_songs(playlist, song_ids)
        return playlist

    @staticmethod
    def _set_songs(playlist, song_ids):
        PlaylistSong.objects.bulk_create(
            [
                PlaylistSong(playlist=playlist, song_id=sid, position=index)
                for index, sid in enumerate(song_ids)
            ]
        )
