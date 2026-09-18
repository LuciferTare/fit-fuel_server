from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from core.pagination import OptionalPagination
from core.permissions import IsAdmin, IsAuthenticatedUser
from core.views import BaseModelViewSet
from music.models import Playlist, Song
from music.serializers import (
    PlaylistCreateSerializer,
    PlaylistSerializer,
    SongCreateSerializer,
    SongSerializer,
)

WRITE_ACTIONS = {
    "create",
    "update",
    "partial_update",
    "partial_update_via_post",
    "destroy",
}


class _MusicViewSet(BaseModelViewSet):
    """Shared behavior: full-array lists by default (opt into pagination via
    `?page_size=`), admin-only writes, authenticated reads, soft-delete on
    destroy, and read-shaped write responses."""

    pagination_class = OptionalPagination
    read_serializer_class = None
    write_serializer_class = None

    def get_permissions(self):
        if self.action in WRITE_ACTIONS:
            return [IsAdmin()]
        return [IsAuthenticatedUser()]

    def get_serializer_class(self):
        if self.action in (
            "create",
            "update",
            "partial_update",
            "partial_update_via_post",
        ):
            return self.write_serializer_class
        return self.read_serializer_class

    def _read_response(self, instance, status_code=200):
        serializer = self.read_serializer_class(
            instance, context=self.get_serializer_context()
        )
        return Response(serializer.data, status=status_code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return self._read_response(instance, status_code=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return self._read_response(instance)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        return Response(status=204)


@extend_schema(tags=["Music"])
class SongViewSet(_MusicViewSet):
    queryset = Song.active_objects.all()
    read_serializer_class = SongSerializer
    write_serializer_class = SongCreateSerializer


@extend_schema(tags=["Music"])
class PlaylistViewSet(_MusicViewSet):
    queryset = Playlist.active_objects.prefetch_related("playlist_songs").all()
    read_serializer_class = PlaylistSerializer
    write_serializer_class = PlaylistCreateSerializer
