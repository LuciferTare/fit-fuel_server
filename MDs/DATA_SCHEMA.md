# FitandFuel — Data Storage Inventory

> **Purpose:** Document every piece of data currently persisted in the app, with types, to inform a migration from local storage to a backend database.

---

## 1. SQLite Database

**File:** `fit_and_fuel.db`  
**Library:** `sqflite`  
**Current version:** 10 (migrated through 10 versions)

---

### Table: `user_profiles`

Stores periodic body measurement snapshots. One new row is inserted each time the user saves a measurement — not updated in-place.

| Column | SQL Type | Dart Type | Nullable | Notes |
|---|---|---|---|---|
| `id` | INTEGER | `int` | No | Primary key, auto-increment |
| `age` | INTEGER | `int?` | Yes | — |
| `gender` | TEXT | `String?` | Yes | `"Male"` or `"Female"` — added v2 |
| `is_correction` | INTEGER | `bool` | No | 0/1 flag; marks a correction entry — added v7 |
| `weight_kg` | REAL | `double?` | Yes | — |
| `height_cm` | REAL | `double?` | Yes | — |
| `chest_cm` | REAL | `double?` | Yes | — |
| `waist_cm` | REAL | `double?` | Yes | — |
| `biceps_cm` | REAL | `double?` | Yes | — |
| `thighs_cm` | REAL | `double?` | Yes | — |
| `neck_cm` | REAL | `double?` | Yes | Added v10 |
| `hip_cm` | REAL | `double?` | Yes | Added v10 |
| `body_fat_percent` | REAL | `double?` | Yes | Added v10 |
| `recorded_at` | TEXT | `String` | No | ISO 8601 datetime string |

---

### Table: `workout_sessions`

One row per workout day (or rest day).

| Column | SQL Type | Dart Type | Nullable | Notes |
|---|---|---|---|---|
| `id` | INTEGER | `int` | No | Primary key, auto-increment |
| `session_date` | TEXT | `String` | No | Format: `DD-MM-YYYY` |
| `duration_minutes` | INTEGER | `int` | No | Default `0` |
| `notes` | TEXT | `String?` | Yes | Free-text user note |
| `calories_burned` | REAL | `double?` | Yes | Calculated and stored — added v3 |
| `is_rest_day` | INTEGER | `bool` | No | 0/1 flag — added v5 |

---

### Table: `session_exercises`

Each exercise block within a session. Multiple rows per session.

| Column | SQL Type | Dart Type | Nullable | Notes |
|---|---|---|---|---|
| `id` | INTEGER | `int` | No | Primary key, auto-increment |
| `session_id` | INTEGER | `int` | No | FK → `workout_sessions.id` (CASCADE DELETE) |
| `exercise_name` | TEXT | `String` | No | Display name of the exercise |
| `body_part` | TEXT | `String?` | Yes | E.g. `"Chest"`, `"Back"` |
| `muscle` | TEXT | `String?` | Yes | E.g. `"Pectoralis Major"` |
| `is_unilateral` | INTEGER | `bool` | No | 0/1 flag — added v6 |

---

### Table: `exercise_sets`

Individual sets within an exercise block.

| Column | SQL Type | Dart Type | Nullable | Notes |
|---|---|---|---|---|
| `id` | INTEGER | `int` | No | Primary key, auto-increment |
| `exercise_id` | INTEGER | `int` | No | FK → `session_exercises.id` (CASCADE DELETE) |
| `set_number` | INTEGER | `int` | No | 1-based ordering |
| `reps` | INTEGER | `int?` | Yes | — |
| `weight_kg` | REAL | `double?` | Yes | — |
| `duration_seconds` | INTEGER | `int?` | Yes | For timed sets/cardio — added v4 |
| `speed_kmh` | REAL | `double?` | Yes | For cardio exercises — added v4 |

---

### Table: `session_rest_breaks`

Rest break entries within a session (separate from exercise rest).

| Column | SQL Type | Dart Type | Nullable | Notes |
|---|---|---|---|---|
| `id` | INTEGER | `int` | No | Primary key, auto-increment |
| `session_id` | INTEGER | `int` | No | FK → `workout_sessions.id` (CASCADE DELETE) |
| `duration_minutes` | INTEGER | `int` | No | Default `0` |
| `sort_index` | INTEGER | `int` | No | Ordering within session — default `0` |

---

### Migration History

| Version | Change |
|---|---|
| v1 → v2 | Added `gender` to `user_profiles` |
| v2 → v3 | Added `calories_burned` to `workout_sessions` |
| v3 → v4 | Added `duration_seconds`, `speed_kmh` to `exercise_sets` |
| v4 → v5 | Added `is_rest_day` to `workout_sessions` |
| v5 → v6 | Added `is_unilateral` to `session_exercises` |
| v6 → v7 | Added `is_correction` to `user_profiles` |
| v7 → v8 | Created `session_rest_breaks` table |
| v8 → v9 | Data correction: fixed muscle mapping for `Machine Hip Adduction` |
| v9 → v10 | Added `neck_cm`, `hip_cm`, `body_fat_percent` to `user_profiles` |

---

## 2. SharedPreferences

**Library:** `shared_preferences ^2.5.3`  
Only 2 keys are stored. Both are in the music controller.

| Key | Type | Purpose |
|---|---|---|
| `last_playlist_id` | `int` | ID of the last active playlist — restores playback state on app relaunch |
| `last_song_idx` | `int` | Index of the last playing song within that playlist |

---

## 3. Temporary Files (Session-scoped)

Written to the system temp directory via `getTemporaryDirectory()`. Cleared by the OS; not user data.

| Filename Pattern | Content Type | Written By | Purpose |
|---|---|---|---|
| `exercise_<filename>` | Binary video | Exercise screen | Extracts bundled asset videos so the video player can read them |
| `art_<filename>` | Image binary | Music controller | Extracts bundled album art for the audio player |
| `Fit&Fuel<DDMMYYYYHHMM>.json` | JSON | Dashboard export | User-triggered full data export file, shared via system share sheet |

---

## 4. Export JSON Format

When the user exports data, the following JSON structure is written to a temp file and shared:

```json
{
  "version": 1,
  "user_profiles": [
    {
      "id": 1,
      "age": 25,
      "gender": "Male",
      "is_correction": 0,
      "weight_kg": 75.5,
      "height_cm": 175.0,
      "chest_cm": 95.0,
      "waist_cm": 80.0,
      "biceps_cm": 35.0,
      "thighs_cm": 55.0,
      "neck_cm": 38.0,
      "hip_cm": 92.0,
      "body_fat_percent": 18.5,
      "recorded_at": "2024-06-26T14:30:00.000"
    }
  ],
  "workout_sessions": [
    {
      "id": 1,
      "session_date": "26-06-2024",
      "duration_minutes": 60,
      "notes": "Felt strong today",
      "calories_burned": 320.5,
      "is_rest_day": 0
    }
  ],
  "session_exercises": [
    {
      "id": 1,
      "session_id": 1,
      "exercise_name": "Bench Press",
      "body_part": "Chest",
      "muscle": "Pectoralis Major",
      "is_unilateral": 0
    }
  ],
  "exercise_sets": [
    {
      "id": 1,
      "exercise_id": 1,
      "set_number": 1,
      "reps": 10,
      "weight_kg": 60.0,
      "duration_seconds": null,
      "speed_kmh": null
    }
  ],
  "session_rest_breaks": [
    {
      "id": 1,
      "session_id": 1,
      "duration_minutes": 2,
      "sort_index": 0
    }
  ]
}
```

---

## 5. Static Asset Data (Read-only, Bundled)

These JSON files are bundled inside the APK. They are loaded into memory at runtime and never written to. They do **not** need to migrate — they can remain in-app assets or be served from a CDN/API.

| Asset File | Model Class | Key Fields |
|---|---|---|
| `assets/data/exercises.json` | `ExerciseModel` | `id: int`, `part: String`, `muscle: String`, `name: String`, `equipment: String`, `unilateral: bool`, `desc: String`, `asset: String` |
| `assets/data/muscle.json` | `MuscleModel` | `id: int`, `part: String`, `muscle: String`, `activeMet: double`, `restSeconds: double`, `restMet: double` |
| `assets/data/songs.json` | `SongModel` | `id: int`, `title: String`, `artist: String`, `thumb: String`, `asset: String`, `duration: int` (seconds) |
| `assets/data/playlists.json` | `PlaylistModel` | `id: int`, `title: String`, `icon: String`, `cover: String`, `color: String`, `songIds: List<int>` |
| `assets/data/recipe.json` | `RecipeModel` | `id: int`, `heading: String`, `description: String`, `ingredients: List<String>`, `tips: List<String>`, `steps: List<String>`, `cal: double`, `carbs: double`, `fat: double`, `protien: double`, `serve: int`, `image: String` |
| `assets/data/quotes.json` | `QuoteModel` | `id: int`, `quote: String`, `author: String` |
| `assets/data/home_exercises.json` | `ExerciseHomeModel` | `id: int`, `image: String`, `part: String`, `bgColor: String`, `symbol: String` |

---

## 6. Computed / Derived Data (Not Stored)

These values are calculated at runtime from the stored data — they are **not** persisted and do not need to be migrated.

| Metric | Derived From |
|---|---|
| BMI | `weight_kg`, `height_cm` from `user_profiles` |
| BMI Category | Computed from BMI value |
| Weekly session count | Count of `workout_sessions` in current week |
| Weekly calories burned | Sum of `calories_burned` from sessions in current week |
| Current streak | Consecutive days with `workout_sessions` rows |
| Weekly calorie analysis | Aggregated `calories_burned` grouped by ISO week |
| Personal records | MAX queries on `exercise_sets` per exercise name |
| Body parts targeted | Distinct `body_part` from `session_exercises` |
| Total sets / reps / volume | Aggregated from `exercise_sets` |

---

## Storage Summary

| Storage | Persistence | Key Data |
|---|---|---|
| SQLite (`fit_and_fuel.db`) | Permanent | All user-generated workout and body measurement data |
| SharedPreferences | Permanent | Last music playlist + song index (2 keys) |
| Temp files | Session / OS-cleared | Extracted videos, album art, export files |
| Bundled assets | Read-only | Exercise library, recipes, music metadata, quotes |
