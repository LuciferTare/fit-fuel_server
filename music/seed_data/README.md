# Music seed data

Drop the Flutter app's bundled exports here before running the seeder:

- `songs.json` — the full 138-song array (`id, title, artist, thumb, asset, duration`)
- `playlists.json` — the full 7-playlist array (`id, title, icon, cover, color, song_ids`)

Then run:

```
python manage.py seed_music
```

This imports every bundled row (keeping its `assets/...` paths, `is_remote=false`)
so backend-created songs/playlists continue from id `139` / `8` and never collide
with the offline bundle.
