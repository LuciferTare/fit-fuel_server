from rest_framework.routers import DefaultRouter

from music.views import PlaylistViewSet, SongViewSet

router = DefaultRouter()
router.register("songs", SongViewSet, basename="song")
router.register("playlists", PlaylistViewSet, basename="playlist")

urlpatterns = router.urls
