from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Gym, UserType
from accounts.tests import make_user
from music.models import Playlist, PlaylistSong, Song

# A tiny, real GIF payload — Pillow detects format from content, not the
# filename, and our _validate_png validator only checks the filename suffix.
_TINY_IMAGE_BYTES = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00"
    b"\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def tiny_png(name="thumb.png"):
    return SimpleUploadedFile(name, _TINY_IMAGE_BYTES, content_type="image/png")


def tiny_opus(name="asset.opus"):
    return SimpleUploadedFile(name, b"fake-opus-bytes", content_type="audio/ogg")


def upload_test_png(client, name="thumb.png"):
    """POST a tiny real image to /api/upload-file/ and return its URL — image
    fields (thumb/icon/cover) now only accept an already-uploaded file's URL,
    not a raw multipart file (asset/audio is unaffected — still a real file)."""
    res = client.post(
        reverse("upload-file"), {"file": tiny_png(name)}, format="multipart"
    )
    return res.json()["data"]["url"]


class SongViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user(
            "9000000260", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        self.other_admin = make_user(
            "9000000261", "Admin2@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        owner = make_user(
            "9000000262", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        self.member = make_user(
            "9000000263", "Member@1234", user_type=UserType.MEMBER, gym=owner
        )
        self.song = Song.objects.create(
            title="Old Title", artist="Old Artist", duration=120,
            is_remote=True, created_by=self.admin,
        )

    def test_admin_can_create_song(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("song-list"),
            {
                "title": "New Song",
                "artist": "New Artist",
                "duration": 200,
                "thumb": upload_test_png(self.client),
                "asset": tiny_opus(),
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["data"]["title"], "New Song")

    def test_admin_can_full_update_song(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.put(
            reverse("song-detail", args=[self.song.id]),
            {
                "title": "Replaced Title",
                "artist": "Replaced Artist",
                "duration": 300,
                "thumb": upload_test_png(self.client),
                "asset": tiny_opus(),
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["title"], "Replaced Title")
        self.song.refresh_from_db()
        self.assertEqual(self.song.title, "Replaced Title")
        self.assertEqual(self.song.duration, 300)

    def test_admin_can_partial_update_song_via_post_without_files(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("song-update", args=[self.song.id]),
            {"title": "Renamed Only"},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.song.refresh_from_db()
        self.assertEqual(self.song.title, "Renamed Only")
        self.assertEqual(self.song.artist, "Old Artist")

    def test_admin_can_delete_song(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(reverse("song-detail", args=[self.song.id]))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.song.refresh_from_db()
        self.assertTrue(self.song.is_deleted)
        list_res = self.client.get(reverse("song-list"))
        ids = [row["id"] for row in list_res.json()["data"]]
        self.assertNotIn(self.song.id, ids)

    def test_any_admin_can_update_or_delete_song_created_by_another_admin(self):
        self.client.force_authenticate(user=self.other_admin)
        res = self.client.post(
            reverse("song-update", args=[self.song.id]),
            {"title": "Touched By Other Admin"},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res = self.client.delete(reverse("song-detail", args=[self.song.id]))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_non_admin_cannot_update_or_delete_song(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            reverse("song-update", args=[self.song.id]),
            {"title": "Should Not Apply"},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        res = self.client.delete(reverse("song-detail", args=[self.song.id]))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_can_still_list_and_retrieve_song(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.get(reverse("song-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.get(reverse("song-detail", args=[self.song.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class PlaylistViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user(
            "9000000270", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        self.other_admin = make_user(
            "9000000271", "Admin2@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        owner = make_user(
            "9000000272", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        self.member = make_user(
            "9000000273", "Member@1234", user_type=UserType.MEMBER, gym=owner
        )
        self.song_a = Song.objects.create(title="Song A", duration=100, is_remote=True)
        self.song_b = Song.objects.create(title="Song B", duration=110, is_remote=True)
        self.playlist = Playlist.objects.create(
            title="Old Playlist", is_remote=True, created_by=self.admin
        )
        PlaylistSong.objects.create(
            playlist=self.playlist, song=self.song_a, position=0
        )

    def test_admin_can_partial_update_playlist_title_without_files(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("playlist-update", args=[self.playlist.id]),
            {"title": "Renamed Playlist"},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.playlist.refresh_from_db()
        self.assertEqual(self.playlist.title, "Renamed Playlist")

    def test_admin_update_with_song_ids_replaces_existing_set(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("playlist-update", args=[self.playlist.id]),
            {"song_ids": [self.song_b.id]},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        song_ids = list(
            self.playlist.playlist_songs.order_by("position").values_list(
                "song_id", flat=True
            )
        )
        self.assertEqual(song_ids, [self.song_b.id])

    def test_admin_can_delete_playlist(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(reverse("playlist-detail", args=[self.playlist.id]))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.playlist.refresh_from_db()
        self.assertTrue(self.playlist.is_deleted)
        list_res = self.client.get(reverse("playlist-list"))
        ids = [row["id"] for row in list_res.json()["data"]]
        self.assertNotIn(self.playlist.id, ids)

    def test_any_admin_can_update_or_delete_playlist_created_by_another_admin(self):
        self.client.force_authenticate(user=self.other_admin)
        res = self.client.post(
            reverse("playlist-update", args=[self.playlist.id]),
            {"title": "Touched By Other Admin"},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res = self.client.delete(reverse("playlist-detail", args=[self.playlist.id]))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_non_admin_cannot_update_or_delete_playlist(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            reverse("playlist-update", args=[self.playlist.id]),
            {"title": "Should Not Apply"},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        res = self.client.delete(reverse("playlist-detail", args=[self.playlist.id]))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
