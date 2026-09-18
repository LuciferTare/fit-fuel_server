# Fit&Fuel API Documentation

**Version:** Phase 1  
**Base URL:** `http://<host>/`  
**Authentication:** JWT Bearer Token — include `Authorization: Bearer <access_token>` on all protected endpoints.

---

## Table of Contents

1.  [Authentication](#1-authentication)
2.  [Gym Master](#2-gym-master)
3.  [User Management](#3-user-management)
4.  [Trainer Panel](#4-trainer-panel)
5.  [Member Panel](#5-member-panel)
6.  [Memberships](#6-memberships)
7.  [Payments](#7-payments)
8.  [Member Payments (Phase 3)](#8-member-payments-phase-3)
9.  [Attendance](#9-attendance)
10. [Reports](#10-reports)
11. [Backup / Sync](#11-backup--sync)
12. [Utility](#12-utility)
13. [Music (Playlists & Songs)](#13-music-playlists--songs)

---

## Permission Roles

| Role                  | Condition                             |
| --------------------- | ------------------------------------- |
| `IsAdmin`             | `user_type == admin`                  |
| `IsGymOwner`          | `user_type == gym_owner`              |
| `IsTrainer`           | `user_type == trainer`                |
| `IsMember`            | `user_type == member`                 |
| `IsAdminOrGymOwner`   | `user_type` in `admin`, `gym_owner`   |

---

## 1. Authentication

### POST `/auth/login/`

Login with phone number and password. Returns JWT access/refresh tokens and a user snapshot.

**Permission:** Public

#### Request

| Field          | Type   | Required | Description             |
| -------------- | ------ | -------- | ----------------------- |
| `phone_number` | string | Yes      | Registered phone number |
| `password`     | string | Yes      | Account password        |

#### Response

| Field               | Type         | Description                                        |
| ------------------- | ------------ | -------------------------------------------------- |
| `detail`            | string       | Status message                                     |
| `refresh`           | string       | JWT refresh token                                  |
| `access`            | string       | JWT access token                                   |
| `user.uuid`         | UUID         | User identifier                                    |
| `user.first_name`   | string       | First name                                         |
| `user.last_name`    | string       | Last name                                          |
| `user.phone_number` | string       | Phone number                                       |
| `user.user_type`    | string       | `admin` \| `gym_owner` \| `trainer` \| `member`    |
| `user.status`       | string       | `active` \| `disabled` \| `suspended` \| `deleted` |
| `user.gym_id`       | UUID \| null | Gym UUID (if applicable)                           |
| `user.trainer_id`   | UUID \| null | Assigned trainer UUID (if applicable)              |

#### Example JSON Request

```json
{
  "phone_number": "9876543210",
  "password": "Str0ng@Pass!"
}
```

#### Example JSON Response

```json
{
  "detail": "Login successful",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "first_name": "Raj",
    "last_name": "Sharma",
    "phone_number": "9876543210",
    "user_type": "gym_owner",
    "status": "active",
    "gym_id": null,
    "trainer_id": null
  }
}
```

#### Error Responses

| Status | When                                                                  | Body                                                               |
| ------ | --------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `401`  | Phone number not registered, or password incorrect                    | message: `"Invalid phone number or password."`                     |
| `403`  | Account `status` is `disabled`                                        | message: `"Account is disabled."`                                  |
| `403`  | Account `status` is `suspended`                                       | message: `"Account is suspended."`                                 |
| `403`  | Account `status` is `deleted` (or `is_deleted = true`)                 | message: `"Account has been deleted."`                             |

---

### POST `/auth/token/refresh/`

Exchange a valid refresh token for a new access token.

**Permission:** Public

#### Request

| Field     | Type   | Required | Description       |
| --------- | ------ | -------- | ----------------- |
| `refresh` | string | Yes      | JWT refresh token |

#### Response

| Field    | Type   | Description          |
| -------- | ------ | -------------------- |
| `access` | string | New JWT access token |

#### Example JSON Request

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Example JSON Response

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

### POST `/auth/logout/`

Blacklist the refresh token, invalidating the session.

**Permission:** Authenticated

#### Request

| Field     | Type   | Required | Description                     |
| --------- | ------ | -------- | ------------------------------- |
| `refresh` | string | Yes      | JWT refresh token to invalidate |

#### Example JSON Request

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Example JSON Response

All responses go through the standard response envelope (`core/renderers.py`) — the
view itself just returns the plain message string, which lands in both `data` and
`message`:

```json
{
  "data": "Logged out successfully.",
  "message": "Logged out successfully.",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

---

### GET `/auth/profile/`

Returns the full profile of the currently authenticated user.

**Permission:** Authenticated

#### Response

| Field              | Type            | Description                                        |
| ------------------ | --------------- | -------------------------------------------------- |
| `uuid`             | UUID            | User identifier                                    |
| `phone_number`     | string          | Phone number                                       |
| `first_name`       | string          | First name                                         |
| `last_name`        | string          | Last name                                          |
| `date_of_birth`    | string \| null  | Date of birth                                      |
| `age`              | integer \| null | Computed age                                       |
| `gender`           | string          | `male` \| `female` \| `other`                      |
| `profile_picture`  | URL \| null     | Profile image URL                                  |
| `experience_level` | string \| null  | Free-text experience level                         |
| `user_type`        | string          | `admin` \| `gym_owner` \| `trainer` \| `member`    |
| `status`           | string          | `active` \| `disabled` \| `suspended` \| `deleted` |
| `gym_id`           | UUID \| null    | Associated gym owner (set on trainer/member accounts; always `null` for the gym owner's own account) |
| `gym_uuid`         | UUID \| null    | The `Gym` master record this account owns (`gym_details`) — only set for `gym_owner` accounts, `null` otherwise |
| `trainer_id`       | UUID \| null    | Assigned trainer                                   |
| `created_at`       | datetime        | Account creation timestamp                         |

#### Example JSON Response

```json
{
  "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "9876543210",
  "first_name": "Raj",
  "last_name": "Sharma",
  "date_of_birth": "1990-05-15",
  "age": 35,
  "gender": "male",
  "profile_picture": "http://localhost:8000/media/profile_pictures/raj.jpg",
  "experience_level": null,
  "user_type": "gym_owner",
  "status": "active",
  "gym_id": null,
  "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "trainer_id": null,
  "created_at": "2025-01-10T08:30:00Z"
}
```

---

### POST `/auth/profile/update/`

Partial update of the currently authenticated user's own profile. Editable fields only — `uuid`, `phone_number`, `user_type`, `status`, `gym_id`, `gym_uuid`, `trainer_id`, and `created_at` are read-only and ignored if sent.

**Permission:** Authenticated

#### Request

| Field              | Type           | Required | Description                                                         |
| ------------------ | -------------- | -------- | -------------------------------------------------------------------- |
| `first_name`       | string         | No       | First name                                                          |
| `last_name`        | string         | No       | Last name                                                           |
| `date_of_birth`    | string \| null | No       | Format: `YYYY-MM-DD`                                                |
| `gender`           | string         | No       | `male` \| `female` \| `other`                                       |
| `profile_picture`  | string \| null | No       | URL from `POST /api/upload-file/` (or `null` to clear)              |
| `experience_level` | string \| null | No       | Free-text experience level                                          |

#### Example JSON Request

```json
{
  "experience_level": "5 years"
}
```

#### Example JSON Response

```json
{
  "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "9876543210",
  "first_name": "Raj",
  "last_name": "Sharma",
  "date_of_birth": "1990-05-15",
  "age": 35,
  "gender": "male",
  "profile_picture": "http://localhost:8000/media/profile_pictures/raj.jpg",
  "experience_level": "5 years",
  "user_type": "gym_owner",
  "status": "active",
  "gym_id": null,
  "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "trainer_id": null,
  "created_at": "2025-01-10T08:30:00Z"
}
```

---

### POST `/auth/change-password/`

Change the authenticated user's password.

**Permission:** Authenticated

#### Request

| Field          | Type   | Required | Description                                                                   |
| -------------- | ------ | -------- | ----------------------------------------------------------------------------- |
| `old_password` | string | Yes      | Current password                                                              |
| `new_password` | string | Yes      | New password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char) |

#### Example JSON Request

```json
{
  "old_password": "OldPass@123",
  "new_password": "NewStr0ng@Pass!"
}
```

#### Example JSON Response

Same envelope pattern as `/auth/logout/` above — the view returns a plain message
string, which lands in both `data` and `message`:

```json
{
  "data": "Password updated successfully.",
  "message": "Password updated successfully.",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

---

## 2. Gym Master

Master record of gym names, referenced by `gym_uuid` on gym-owner accounts (see [User Management](#3-user-management)). Endpoints under `/gyms/` support pagination, search, and ordering.

**Permission:** `IsAdmin` for create/delete/enable. Update (`PUT` / `POST .../update/`) is `IsAdmin` **or** the `gym_owner` who owns that gym (a gym owner may only edit their own gym — identified by their `gym_details`/`gym_uuid` — and only ever has `name`, `gym_picture`, `latitude`, `longitude` to change; attempting to edit another gym returns `404`). Any authenticated user (`admin`, `gym_owner`, `trainer`, `member`) can list/retrieve.

**Location is compulsory going forward:** `latitude`/`longitude` are required on create and on a full `PUT`, and can never be set to `null` through the API — a partial `POST .../update/` may omit them (leaves the location unchanged) or change them, but an explicit `null` is rejected. This means any gym created (or since edited) through the API always has a location; the two fields are still nullable at the DB layer only so that legacy rows predating this constraint keep working, so a gym seeded before this rule existed can in principle still have no location. This backs the 50m geofence check on [Attendance](#9-attendance) check-in/out, which handles that "no location" case explicitly rather than assuming it can't happen.

**Common query parameters:**

| Param       | Description                                 |
| ----------- | ------------------------------------------- |
| `page`      | Page number                                 |
| `page_size` | Results per page                            |
| `search`    | Search against `name`                       |
| `ordering`  | Sort field (prefix with `-` for descending) |

---

### GET `/gyms/`

List all gyms.

**Permission:** Authenticated (any role)

#### Response (paginated list)

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
      "name": "Iron Paradise",
      "gym_picture": null,
      "latitude": "18.520430",
      "longitude": "73.856743"
    }
  ]
}
```

---

### POST `/gyms/`

Create a new gym master record.

**Permission:** `IsAdmin`

#### Request

| Field         | Type           | Required | Description                            |
| ------------- | -------------- | -------- | ---------------------------------------- |
| `name`        | string         | Yes      | Gym name                                |
| `gym_picture` | string \| null | No       | URL from `POST /api/upload-file/`       |
| `latitude`    | decimal        | Yes      | Gym latitude (up to 9,6 precision)       |
| `longitude`   | decimal        | Yes      | Gym longitude (up to 9,6 precision)      |

#### Example JSON Request

```json
{
  "name": "Iron Paradise",
  "latitude": "18.520430",
  "longitude": "73.856743"
}
```

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Iron Paradise",
  "gym_picture": null,
  "latitude": "18.520430",
  "longitude": "73.856743"
}
```

---

### GET `/gyms/{uuid}/`

Retrieve a single gym by UUID.

**Permission:** Authenticated (any role)

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Iron Paradise",
  "gym_picture": "http://localhost:8000/media/gym_pictures/iron_paradise.jpg",
  "latitude": "18.520430",
  "longitude": "73.856743"
}
```

---

### PUT `/gyms/{uuid}/`

Full update of a gym record.

**Permission:** `IsAdmin`, or the `gym_owner` who owns this gym (via `gym_details`) — a gym owner may only target their own gym; any other `uuid` returns `404`.

#### Request

| Field         | Type           | Required | Description                            |
| ------------- | -------------- | -------- | ---------------------------------------- |
| `name`        | string         | Yes      | Gym name                                |
| `gym_picture` | string \| null | No       | URL from `POST /api/upload-file/`       |
| `latitude`    | decimal        | Yes      | Gym latitude (up to 9,6 precision)       |
| `longitude`   | decimal        | Yes      | Gym longitude (up to 9,6 precision)      |

#### Example JSON Request

```json
{
  "name": "Renamed Gym",
  "latitude": "18.520430",
  "longitude": "73.856743"
}
```

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Renamed Gym",
  "gym_picture": null,
  "latitude": "18.520430",
  "longitude": "73.856743"
}
```

---

### POST `/gyms/{uuid}/update/`

Partial update of a gym record. `latitude`/`longitude` may be omitted (location stays
unchanged) or replaced, but never sent as `null`.

**Permission:** `IsAdmin`, or the `gym_owner` who owns this gym (via `gym_details`) — a gym owner may only target their own gym; any other `uuid` returns `404`.

#### Example JSON Request

```json
{
  "name": "Renamed Gym",
  "latitude": "19.076090",
  "longitude": "72.877426"
}
```

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Renamed Gym",
  "gym_picture": null,
  "latitude": "19.076090",
  "longitude": "72.877426"
}
```

---

### DELETE `/gyms/{uuid}/`

Soft-delete a gym record (sets `is_deleted = true`).

**Permission:** `IsAdmin`

#### Response

`HTTP 204 No Content` — empty body.

---

### POST `/gyms/{uuid}/enable/`

Re-enable a soft-deleted gym record (sets `is_deleted = false`).

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Iron Paradise",
  "gym_picture": null,
  "latitude": "18.520430",
  "longitude": "73.856743"
}
```

---

## 3. User Management

All endpoints under `/users/` support pagination, filtering, searching, and ordering.

**Common query parameters:**

| Param       | Description                                 |
| ----------- | ------------------------------------------- |
| `page`      | Page number                                 |
| `page_size` | Results per page                            |
| `search`    | Search against name and phone fields        |
| `ordering`  | Sort field (prefix with `-` for descending) |
| `status`    | Filter by user status                       |

---

### GET `/users/gym-owners/`

List all gym owners. Supports filtering, search, and ordering. Each entry includes `trainer_count` and `member_count` — the number of active (non-deleted) trainers and members belonging to that gym owner.

**Permission:** `IsAdmin`

#### Response (paginated list)

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "data": [
    {
      "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "phone_number": "9876543210",
      "first_name": "Raj",
      "last_name": "Sharma",
      "date_of_birth": "1985-03-20",
      "age": 40,
      "gender": "male",
      "profile_picture": null,
      "user_type": "gym_owner",
      "status": "active",
      "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
      "trainer_limit": 5,
      "trainer_count": 3,
      "member_count": 42,
      "membership_start": "2026-01-15",
      "membership_end": "2026-02-14",
      "created_at": "2025-01-10T08:30:00Z"
    }
  ]
}
```

---

### POST `/users/gym-owners/`

Create a new gym owner account.

**Permission:** `IsAdmin`

A duplicate `phone_number` is rejected with `HTTP 409` before the serializer even
runs (checked directly in the view):

```json
{
  "detail": "This phone number is already registered."
}
```

(this raw body is what DRF's exception produces; through the standard response
envelope it surfaces as `message: "This phone number is already registered."` with
`data: null`, `status: 409`)

#### Request

| Field             | Type           | Required | Description                                                                                           |
| ----------------- | -------------- | -------- | ----------------------------------------------------------------------------------------------------- |
| `phone_number`    | string         | Yes      | Must be unique, max 15 chars — `409` if already registered (see above)                                |
| `password`        | string         | Yes      | Strong password (min 8 chars, mixed case, digit, special char)                                        |
| `first_name`      | string         | Yes      | First name                                                                                            |
| `last_name`       | string         | Yes      | Last name                                                                                             |
| `date_of_birth`   | string \| null | No       | Format: `YYYY-MM-DD`                                                                                  |
| `gender`          | string         | Yes      | `male` \| `female` \| `other`                                                                         |
| `profile_picture` | string \| null | No       | URL from `POST /api/upload-file/`                                                                     |
| `gym_name`        | string         | Yes      | Name of the gym owned by this account; stored in a separate `Gym` master record                       |
| `gym_latitude`    | decimal        | Yes      | Latitude of the gym (up to 9,6 precision); stored on the same `Gym` master record                     |
| `gym_longitude`   | decimal        | Yes      | Longitude of the gym (up to 9,6 precision); stored on the same `Gym` master record                    |
| `membership`      | string         | Yes      | `Monthly` \| `Quarterly` \| `Half-Yearly` \| `Yearly` — see below for how `membership_end` is derived |

`membership_start` is set to today's date and `membership_end` is computed from it (same day N months later, minus one day):

| `membership`  | Months | Example (`membership_start` = 2026-01-15) |
| ------------- | ------ | ----------------------------------------- |
| `Monthly`     | 1      | `membership_end` = 2026-02-14             |
| `Quarterly`   | 3      | `membership_end` = 2026-04-14             |
| `Half-Yearly` | 6      | `membership_end` = 2026-07-14             |
| `Yearly`      | 12     | `membership_end` = 2027-01-14             |

If the start day doesn't exist in the target month (e.g. Jan 31 + 1 month), it's clamped to that month's last day before subtracting one day.

#### Example JSON Request

```json
{
  "phone_number": "9876543210",
  "password": "Str0ng@Pass!",
  "first_name": "Raj",
  "last_name": "Sharma",
  "date_of_birth": "1985-03-20",
  "gender": "male",
  "gym_name": "Iron Paradise",
  "gym_latitude": "18.520430",
  "gym_longitude": "73.856743",
  "membership": "Monthly"
}
```

#### Example JSON Response

```json
{
  "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "9876543210",
  "first_name": "Raj",
  "last_name": "Sharma",
  "date_of_birth": "1985-03-20",
  "gender": "male",
  "profile_picture": null,
  "status": "active",
  "created_at": "2026-06-30T10:00:00Z"
}
```

---

### GET `/users/gym-owners/{uuid}/`

Retrieve a single gym owner by UUID. The response includes `trainer_count`/`member_count` (active trainer and member totals for this gym owner) and a `trainers` list — every active trainer assigned to this gym owner's gym.

**Permission:** `IsAdmin`

| `trainers[]` field | Type            | Description                   |
| ------------------ | --------------- | ----------------------------- |
| `uuid`             | UUID            | Trainer UUID                  |
| `name`             | string          | Trainer's full name           |
| `phone_number`     | string          | Trainer's phone number        |
| `date_of_birth`    | string \| null  | Date of birth                 |
| `age`              | integer \| null | Computed age                  |
| `gender`           | string          | `male` \| `female` \| `other` |
| `created_at`       | datetime        | Account creation timestamp    |

#### Example JSON Response

```json
{
  "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "9876543210",
  "first_name": "Raj",
  "last_name": "Sharma",
  "date_of_birth": "1985-03-20",
  "age": 40,
  "gender": "male",
  "profile_picture": null,
  "user_type": "gym_owner",
  "status": "active",
  "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "trainer_limit": 5,
  "trainer_count": 1,
  "member_count": 0,
  "membership_start": "2026-01-15",
  "membership_end": "2026-02-14",
  "created_at": "2025-01-10T08:30:00Z",
  "trainers": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Priya Nair",
      "phone_number": "9000000001",
      "date_of_birth": "1995-07-12",
      "age": 30,
      "gender": "female",
      "created_at": "2025-03-01T09:00:00Z"
    }
  ]
}
```

---

### PUT `/users/gym-owners/{uuid}/`

Full update of a gym owner record.

**Permission:** `IsAdmin`

#### Request

Uses the same writable fields as `GymOwnerDetailSerializer` — `phone_number`, `first_name`, `last_name`, `date_of_birth`, `gender`, `profile_picture`, `status`, `trainer_limit`, `membership_start`, `membership_end`. Note this is a different serializer than `POST /users/gym-owners/`: `gym_name` and `membership` are create-only and cannot be changed via PUT/`update/`.

Of those, only `phone_number` is actually required on a full `PUT` (it has no default and isn't blank-able on the model) — every other writable field is optional even on `PUT`, because the model defines each with `blank=True`/`null=True` or a default value, which `GymOwnerDetailSerializer` inherits as `required=False`. Omitting an optional field on `PUT` leaves it at its current DB value (DRF doesn't reset omitted fields on a `ModelSerializer` — it only overwrites what's present in the payload).

`phone_number` must remain unique across all users; reusing another account's number returns a validation error.

`trainer_limit` (integer, min `0`) is the max number of active trainers this gym owner may create (see the "Trainer limit" note under `POST /users/trainers/`). Admins can override it here at any time, regardless of the default of `5`.

#### Example JSON Request

```json
{
  "first_name": "Rajesh",
  "last_name": "Sharma",
  "date_of_birth": "1985-03-20",
  "gender": "male",
  "status": "active",
  "trainer_limit": 10,
  "membership_start": "2026-01-15",
  "membership_end": "2026-02-14"
}
```

#### Example JSON Response

```json
{
  "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "9876543210",
  "first_name": "Rajesh",
  "last_name": "Sharma",
  "date_of_birth": "1985-03-20",
  "age": 40,
  "gender": "male",
  "profile_picture": null,
  "user_type": "gym_owner",
  "status": "active",
  "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "trainer_limit": 10,
  "trainer_count": 1,
  "member_count": 0,
  "membership_start": "2026-01-15",
  "membership_end": "2026-02-14",
  "created_at": "2025-01-10T08:30:00Z"
}
```

---

### POST `/users/gym-owners/{uuid}/update/`

Partial update of a gym owner record. Also used by admins to override `trainer_limit` alone, without resending every other field.

**Permission:** `IsAdmin`

#### Example JSON Request

```json
{
  "trainer_limit": 10
}
```

#### Example JSON Response

```json
{
  "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "9876543210",
  "first_name": "Rajesh",
  "last_name": "Sharma",
  "date_of_birth": "1985-03-20",
  "age": 40,
  "gender": "male",
  "profile_picture": null,
  "user_type": "gym_owner",
  "status": "active",
  "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "trainer_limit": 10,
  "trainer_count": 1,
  "member_count": 0,
  "membership_start": "2026-01-15",
  "membership_end": "2026-02-14",
  "created_at": "2025-01-10T08:30:00Z"
}
```

---

### DELETE `/users/gym-owners/{uuid}/`

Soft-delete a gym owner (sets `is_deleted = true`).

**Permission:** `IsAdmin`

#### Response

`HTTP 204 No Content` — empty body.

---

### POST `/users/gym-owners/{uuid}/disable/`

Disable a gym owner account (sets `status = disabled`).

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "9876543210",
  "first_name": "Raj",
  "last_name": "Sharma",
  "date_of_birth": "1985-03-20",
  "age": 40,
  "gender": "male",
  "profile_picture": null,
  "user_type": "gym_owner",
  "status": "disabled",
  "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "trainer_limit": 5,
  "trainer_count": 1,
  "member_count": 0,
  "membership_start": "2026-01-15",
  "membership_end": "2026-02-14",
  "created_at": "2025-01-10T08:30:00Z"
}
```

---

### POST `/users/gym-owners/{uuid}/enable/`

Re-enable a gym owner account (sets `status = active`).

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "9876543210",
  "first_name": "Raj",
  "last_name": "Sharma",
  "date_of_birth": "1985-03-20",
  "age": 40,
  "gender": "male",
  "profile_picture": null,
  "user_type": "gym_owner",
  "status": "active",
  "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "trainer_limit": 5,
  "trainer_count": 1,
  "member_count": 0,
  "membership_start": "2026-01-15",
  "membership_end": "2026-02-14",
  "created_at": "2025-01-10T08:30:00Z"
}
```

---

### GET `/users/trainers/`

List trainers. Gym owners see only trainers belonging to their own gym; admins see every trainer across all gyms.

**Permission:** `IsAdminOrGymOwner`  
**Filter fields:** `status`  
**Search fields:** `first_name`, `last_name`, `phone_number`

#### Example JSON Response

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "phone_number": "9000000001",
      "first_name": "Priya",
      "last_name": "Nair",
      "date_of_birth": "1995-07-12",
      "age": 30,
      "gender": "female",
      "profile_picture": null,
      "user_type": "trainer",
      "status": "active",
      "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "created_at": "2025-03-01T09:00:00Z"
    }
  ]
}
```

---

### POST `/users/trainers/`

Create a new trainer under the requesting gym owner's gym.

**Permission:** `IsGymOwner`

**Trainer limit:** Each gym owner may have at most `trainer_limit` active trainers (default `5`; soft-deleted trainers don't count toward this). Increasing it normally requires an additional payment, which is not yet implemented — until then, an admin can override a gym owner's `trainer_limit` directly via `PUT`/`POST /users/gym-owners/{uuid}/update/`. Exceeding the current limit returns:

```json
{
  "trainer_limit": "Trainer limit of 5 has been reached."
}
```

with HTTP 400.

A duplicate `phone_number` is rejected with `HTTP 409` before the serializer even
runs, same as `POST /users/gym-owners/` above — see that section for the exact
response shape.

#### Request

| Field              | Type           | Required | Description                                              |
| ------------------ | -------------- | -------- | --------------------------------------------------------- |
| `phone_number`     | string         | Yes      | Must be unique, max 15 chars — `409` if already registered |
| `password`         | string         | Yes      | Strong password                                           |
| `first_name`       | string         | Yes      | First name                                                 |
| `last_name`        | string         | Yes      | Last name                                                  |
| `date_of_birth`    | string \| null | No       | Format: `YYYY-MM-DD`                                       |
| `gender`           | string         | Yes      | `male` \| `female` \| `other`                              |
| `profile_picture`  | string \| null | No       | URL from `POST /api/upload-file/`                          |
| `experience_level` | string \| null | No       | Free-text experience level                                 |

#### Example JSON Request

```json
{
  "phone_number": "9000000001",
  "password": "Trainer@123",
  "first_name": "Priya",
  "last_name": "Nair",
  "date_of_birth": "1995-07-12",
  "gender": "female",
  "experience_level": "3 years"
}
```

#### Example JSON Response

```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "phone_number": "9000000001",
  "first_name": "Priya",
  "last_name": "Nair",
  "date_of_birth": "1995-07-12",
  "age": 30,
  "gender": "female",
  "profile_picture": null,
  "experience_level": "3 years",
  "user_type": "trainer",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "created_at": "2026-06-30T10:00:00Z"
}
```

---

### GET `/users/trainers/{uuid}/`

Retrieve a trainer by UUID. Gym owners can only retrieve trainers belonging to their own gym; admins can retrieve any trainer.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Response

```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "phone_number": "9000000001",
  "first_name": "Priya",
  "last_name": "Nair",
  "date_of_birth": "1995-07-12",
  "age": 30,
  "gender": "female",
  "profile_picture": null,
  "user_type": "trainer",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "created_at": "2025-03-01T09:00:00Z"
}
```

---

### PUT `/users/trainers/{uuid}/`

Full update of a trainer record.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a trainer belonging to another gym owner returns `404` (the record isn't in that gym owner's queryset at all, same object-level scoping as [Gym Master](#2-gym-master)).

#### Example JSON Request

```json
{
  "first_name": "Priyanka",
  "last_name": "Nair",
  "gender": "female",
  "status": "active"
}
```

#### Example JSON Response

```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "phone_number": "9000000001",
  "first_name": "Priyanka",
  "last_name": "Nair",
  "date_of_birth": "1995-07-12",
  "age": 30,
  "gender": "female",
  "profile_picture": null,
  "user_type": "trainer",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "created_at": "2025-03-01T09:00:00Z"
}
```

---

### POST `/users/trainers/{uuid}/update/`

Partial update of a trainer record. Optionally update the password.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a trainer belonging to another gym owner returns `404`.

#### Example JSON Request

```json
{
  "password": "NewTrainer@456"
}
```

#### Example JSON Response

```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "phone_number": "9000000001",
  "first_name": "Priya",
  "last_name": "Nair",
  "date_of_birth": "1995-07-12",
  "age": 30,
  "gender": "female",
  "profile_picture": null,
  "user_type": "trainer",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "created_at": "2025-03-01T09:00:00Z"
}
```

---

### DELETE `/users/trainers/{uuid}/`

Soft-delete a trainer.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a trainer belonging to another gym owner returns `404`.

#### Response

`HTTP 204 No Content` — empty body.

---

### POST `/users/trainers/{uuid}/disable/`

Disable a trainer account.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a trainer belonging to another gym owner returns `404`.

#### Example JSON Response

```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "phone_number": "9000000001",
  "first_name": "Priya",
  "last_name": "Nair",
  "date_of_birth": "1995-07-12",
  "age": 30,
  "gender": "female",
  "profile_picture": null,
  "user_type": "trainer",
  "status": "disabled",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "created_at": "2025-03-01T09:00:00Z"
}
```

---

### POST `/users/trainers/{uuid}/enable/`

Re-enable a trainer account (sets `status = active`).

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a trainer belonging to another gym owner returns `404`.

#### Example JSON Response

```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "phone_number": "9000000001",
  "first_name": "Priya",
  "last_name": "Nair",
  "date_of_birth": "1995-07-12",
  "age": 30,
  "gender": "female",
  "profile_picture": null,
  "user_type": "trainer",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "created_at": "2025-03-01T09:00:00Z"
}
```

---

### GET `/users/members/`

List members. Gym owners see only members belonging to their own gym; admins see every member across all gyms.

**Permission:** `IsAdminOrGymOwner`  
**Filter fields:** `status`, `gender`, `trainer`  
**Search fields:** `first_name`, `last_name`, `phone_number`

#### Example JSON Response

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "phone_number": "9111111111",
      "first_name": "Amit",
      "last_name": "Verma",
      "date_of_birth": "2000-11-05",
      "age": 25,
      "gender": "male",
      "profile_picture": null,
      "user_type": "member",
      "status": "active",
      "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "created_at": "2025-06-01T07:00:00Z"
    }
  ]
}
```

---

### POST `/users/members/`

Create a new member under the requesting gym owner's gym.

**Permission:** `IsGymOwner`

A duplicate `phone_number` is rejected with `HTTP 409` before the serializer even
runs, same as `POST /users/gym-owners/` above — see that section for the exact
response shape.

#### Request

| Field              | Type           | Required | Description                                              |
| ------------------ | -------------- | -------- | ---------------------------------------------------------- |
| `phone_number`     | string         | Yes      | Must be unique, max 15 chars — `409` if already registered |
| `password`         | string         | Yes      | Strong password                                             |
| `first_name`       | string         | Yes      | First name                                                  |
| `last_name`        | string         | Yes      | Last name                                                   |
| `date_of_birth`    | string \| null | No       | Format: `YYYY-MM-DD`                                        |
| `gender`           | string         | Yes      | `male` \| `female` \| `other`                               |
| `profile_picture`  | string \| null | No       | URL from `POST /api/upload-file/`                           |
| `experience_level` | string \| null | No       | Free-text experience level                                  |
| `trainer_uuid`     | UUID \| null   | No       | UUID of a trainer in the same gym                           |

#### Example JSON Request

```json
{
  "phone_number": "9111111111",
  "password": "Member@123",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "gender": "male",
  "experience_level": "Beginner",
  "trainer_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "profile_picture": null,
  "experience_level": "Beginner",
  "user_type": "member",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2026-06-30T10:00:00Z"
}
```

---

### GET `/users/members/{uuid}/`

Retrieve a member by UUID. Gym owners can only retrieve members belonging to their own gym; admins can retrieve any member.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "profile_picture": null,
  "user_type": "member",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2025-06-01T07:00:00Z"
}
```

---

### PUT `/users/members/{uuid}/`

Full update of a member record.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a member belonging to another gym owner returns `404`.

`trainer_id` (UUID, nullable) is a directly-writable field here — a gym owner can
reassign (or clear) a member's trainer through this endpoint's payload, not only via
the dedicated [`assign-trainer`](#post-usersmembersuuidassign-trainer) action. It's
validated the same way: the referenced trainer must exist and belong to the same gym.

#### Example JSON Request

```json
{
  "first_name": "Amitabh",
  "last_name": "Verma",
  "gender": "male",
  "status": "active",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amitabh",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "profile_picture": null,
  "user_type": "member",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2025-06-01T07:00:00Z"
}
```

---

### POST `/users/members/{uuid}/update/`

Partial update of a member record.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a member belonging to another gym owner returns `404`.

Like `PUT` above, `trainer_id` is directly writable here too — send it to reassign
(or, as `null`, to clear) the member's trainer without calling the dedicated
`assign-trainer` action.

#### Example JSON Request

```json
{
  "password": "NewMember@456"
}
```

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "profile_picture": null,
  "user_type": "member",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2025-06-01T07:00:00Z"
}
```

---

### DELETE `/users/members/{uuid}/`

Soft-delete a member.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a member belonging to another gym owner returns `404`.

#### Response

`HTTP 204 No Content` — empty body.

---

### POST `/users/members/{uuid}/disable/`

Disable a member account.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a member belonging to another gym owner returns `404`.

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "profile_picture": null,
  "user_type": "member",
  "status": "disabled",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2025-06-01T07:00:00Z"
}
```

---

### POST `/users/members/{uuid}/enable/`

Re-enable a member account (sets `status = active`).

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a member belonging to another gym owner returns `404`.

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "profile_picture": null,
  "user_type": "member",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2025-06-01T07:00:00Z"
}
```

---

### POST `/users/members/{uuid}/assign-trainer/`

Assign or reassign a trainer to a member.

**Permission:** `IsGymOwner`. Scoped to the requesting gym owner's own gym — targeting a member belonging to another gym owner returns `404`; the `trainer_uuid` must also belong to a trainer in that same gym.

#### Request

| Field          | Type | Required | Description                       |
| -------------- | ---- | -------- | --------------------------------- |
| `trainer_uuid` | UUID | Yes      | UUID of a trainer in the same gym |

#### Example JSON Request

```json
{
  "trainer_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "profile_picture": null,
  "user_type": "member",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2025-06-01T07:00:00Z"
}
```

---

## 4. Trainer Panel

Read-only access for trainers to see their assigned members.

### GET `/trainer/members/`

List all members assigned to the authenticated trainer.

**Permission:** `IsTrainer`  
**Search fields:** `first_name`, `last_name`, `phone_number`  
**Ordering fields:** `first_name`, `last_name`, `created_at`

#### Example JSON Response

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "data": [
    {
      "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "phone_number": "9111111111",
      "first_name": "Amit",
      "last_name": "Verma",
      "date_of_birth": "2000-11-05",
      "age": 25,
      "gender": "male",
      "profile_picture": null,
      "user_type": "member",
      "status": "active",
      "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "created_at": "2025-06-01T07:00:00Z"
    }
  ]
}
```

---

### GET `/trainer/members/{uuid}/`

Retrieve the profile of a specific member assigned to the authenticated trainer.

**Permission:** `IsTrainer`

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "profile_picture": null,
  "user_type": "member",
  "status": "active",
  "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2025-06-01T07:00:00Z"
}
```

---

## 5. Member Panel

### GET `/member/profile/`

Retrieve the authenticated member's own profile.

**Permission:** `IsMember`

#### Response

| Field               | Type           | Description                   |
| ------------------- | -------------- | ------------------------------ |
| `uuid`              | UUID           | Member identifier (read-only) |
| `phone_number`      | string         | Phone number (read-only)      |
| `first_name`        | string         | First name                    |
| `last_name`         | string         | Last name                     |
| `profile_picture`   | URL \| null    | Profile image URL             |
| `date_of_birth`     | string         | Date of birth (read-only)     |
| `age`               | integer        | Computed age (read-only)      |
| `gender`            | string         | `male` \| `female` \| `other` |
| `experience_level`  | string \| null | Free-text experience level    |

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amit",
  "last_name": "Verma",
  "profile_picture": null,
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "experience_level": "Beginner"
}
```

---

### POST `/member/profile/`

Update the authenticated member's own profile. Only editable fields can be changed.

**Permission:** `IsMember`

#### Request

| Field               | Type           | Required | Description                                            |
| ------------------- | -------------- | -------- | -------------------------------------------------------- |
| `first_name`        | string         | No       | First name                                             |
| `last_name`         | string         | No       | Last name                                              |
| `profile_picture`   | string \| null | No       | URL from `POST /api/upload-file/` (or `null` to clear) |
| `gender`            | string         | No       | `male` \| `female` \| `other`                          |
| `experience_level`  | string \| null | No       | Free-text experience level                             |

#### Example JSON Request

```json
{
  "first_name": "Amitabh",
  "gender": "male"
}
```

#### Example JSON Response

```json
{
  "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "phone_number": "9111111111",
  "first_name": "Amitabh",
  "last_name": "Verma",
  "profile_picture": null,
  "date_of_birth": "2000-11-05",
  "age": 25,
  "gender": "male",
  "experience_level": "Beginner"
}
```

---

## 6. Memberships

### GET `/memberships/`

List membership records. Gym owners see only their gym's memberships.

**Permission:** `IsAdminOrGymOwner`  
**Filter fields:** `status`, `member`, `payment_mode`  
**Ordering fields:** `start_date`, `end_date`, `created_at`

#### Example JSON Response

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "start_date": "2026-06-01",
      "end_date": "2026-07-01",
      "plan": "Monthly",
      "amount_paid": "1500.00",
      "payment_mode": "cash",
      "status": "active",
      "created_at": "2026-06-01T08:00:00Z",
      "updated_at": "2026-06-01T08:00:00Z"
    }
  ]
}
```

---

### POST `/memberships/`

Create a new membership record for a member.

**Permission:** `IsAdminOrGymOwner`

#### Request

| Field          | Type    | Required | Description                                   |
| -------------- | ------- | -------- | --------------------------------------------- |
| `member`       | UUID    | Yes      | Member's UUID (must be `user_type == member`) |
| `start_date`   | string  | Yes      | Membership start date                         |
| `end_date`     | string  | Yes      | Membership end date (must be >= `start_date`) |
| `plan`         | string  | No       | Plan name, max 100 chars                      |
| `amount_paid`  | decimal | Yes      | Amount paid (e.g., `1500.00`)                 |
| `payment_mode` | string  | Yes      | `cash` \| `online`                            |

#### Example JSON Request

```json
{
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-06-01",
  "end_date": "2026-07-01",
  "plan": "Monthly",
  "amount_paid": "1500.00",
  "payment_mode": "cash"
}
```

#### Example JSON Response

```json
{
  "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-06-01",
  "end_date": "2026-07-01",
  "plan": "Monthly",
  "amount_paid": "1500.00",
  "payment_mode": "cash",
  "status": "active",
  "created_at": "2026-06-30T10:00:00Z",
  "updated_at": "2026-06-30T10:00:00Z"
}
```

---

### GET `/memberships/{uuid}/`

Retrieve a specific membership record.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Response

```json
{
  "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-06-01",
  "end_date": "2026-07-01",
  "plan": "Monthly",
  "amount_paid": "1500.00",
  "payment_mode": "cash",
  "status": "active",
  "created_at": "2026-06-01T08:00:00Z",
  "updated_at": "2026-06-01T08:00:00Z"
}
```

---

### PUT `/memberships/{uuid}/`

Full update of a membership record.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Request

```json
{
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-06-01",
  "end_date": "2026-08-01",
  "plan": "Bi-Monthly",
  "amount_paid": "2800.00",
  "payment_mode": "online"
}
```

#### Example JSON Response

```json
{
  "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-06-01",
  "end_date": "2026-08-01",
  "plan": "Bi-Monthly",
  "amount_paid": "2800.00",
  "payment_mode": "online",
  "status": "active",
  "created_at": "2026-06-01T08:00:00Z",
  "updated_at": "2026-06-30T11:00:00Z"
}
```

---

### POST `/memberships/{uuid}/update/`

Partial update of a membership record.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Request

```json
{
  "end_date": "2026-08-01"
}
```

#### Example JSON Response

```json
{
  "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-06-01",
  "end_date": "2026-08-01",
  "plan": "Monthly",
  "amount_paid": "1500.00",
  "payment_mode": "cash",
  "status": "active",
  "created_at": "2026-06-01T08:00:00Z",
  "updated_at": "2026-06-30T11:00:00Z"
}
```

---

### DELETE `/memberships/{uuid}/`

Soft-delete a membership record.

**Permission:** `IsAdminOrGymOwner`

#### Response

`HTTP 204 No Content` — empty body.

---

## 7. Payments

Read-only endpoints for fetching payments **received by** the requesting user:

- **Admin** — sees payments made by gym owners to the platform.
- **Gym Owner** — sees payments made by their gym's members.

Trainers and members have no access. Write operations (POST/PUT/DELETE) are not available on these endpoints.

### GET `/payments/`

List payments received by the requesting user, newest first (by `payment_date`).

**Permission:** `IsAdminOrGymOwner`

**Query parameters:**

| Param       | Type   | Required | Description                                                               |
| ----------- | ------ | -------- | ------------------------------------------------------------------------- |
| `search`    | string | No       | Case-insensitive partial match on payer name, gym name, or invoice number |
| `status`    | string | No       | `paid` \| `pending` \| `overdue`                                          |
| `page`      | int    | No       | Page number (default 1)                                                   |
| `page_size` | int    | No       | Items per page (default 20, max 100)                                      |

**Response fields:**

| Field             | Type    | Description                                                      |
| ----------------- | ------- | ---------------------------------------------------------------- |
| `uuid`            | UUID    | Payment UUID                                                     |
| `invoice_number`  | string  | Auto-generated invoice number (`INV-...`)                        |
| `member_name`     | string  | Payer's full name (the member; in the Admin view, the gym owner) |
| `member_phone`    | string  | Payer's phone number                                             |
| `gym_name`        | string  | Name of the gym the payment belongs to (nullable)                |
| `amount`          | decimal | Payment amount                                                   |
| `status`          | string  | `paid` \| `pending` \| `overdue`                                 |
| `method`          | string  | `cash` \| `online`                                               |
| `membership_plan` | string  | Plan of the linked membership; `null` for gym-owner payments     |
| `payment_date`    | string  | Date the payment was made (`YYYY-MM-DD`)                         |
| `due_date`        | string  | Due date for pending payments (`YYYY-MM-DD`, nullable)           |

#### Example JSON Response

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "uuid": "d4e5f6a7-b8c9-0123-def0-234567890123",
      "invoice_number": "INV-20260715-3F2A9C",
      "member_name": "John Doe",
      "member_phone": "9876543210",
      "gym_name": "Iron Temple",
      "amount": 1500.0,
      "status": "paid",
      "method": "cash",
      "membership_plan": "Monthly",
      "payment_date": "2026-07-01",
      "due_date": null
    }
  ]
}
```

---

### GET `/payments/{uuid}/`

Retrieve a single payment in detail. Same scoping as the list — a payment outside the requesting user's scope returns `404`.

**Permission:** `IsAdminOrGymOwner`

**Response fields:** all list fields plus:

| Field        | Type     | Description                                    |
| ------------ | -------- | ---------------------------------------------- |
| `member`     | UUID     | UUID of the payer (member or gym owner)        |
| `membership` | UUID     | UUID of the linked membership (`null` if none) |
| `paid_on`    | datetime | Full payment timestamp                         |
| `created_at` | datetime | Record creation timestamp                      |
| `updated_at` | datetime | Record update timestamp                        |

#### Example JSON Response

```json
{
  "uuid": "d4e5f6a7-b8c9-0123-def0-234567890123",
  "invoice_number": "INV-20260715-3F2A9C",
  "member_name": "John Doe",
  "member_phone": "9876543210",
  "gym_name": "Iron Temple",
  "amount": 1500.0,
  "status": "paid",
  "method": "cash",
  "membership_plan": "Monthly",
  "payment_date": "2026-07-01",
  "due_date": null,
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "paid_on": "2026-07-01T08:00:00Z",
  "created_at": "2026-07-01T08:00:00Z",
  "updated_at": "2026-07-01T08:00:00Z"
}
```

---

## 8. Member Payments (Phase 3)

Despite the section name and the `/api/payments/` path, this endpoint does **not**
create or touch an `accounts.models.Payment` row — no `Payment` is involved at all.
`POST` here creates a brand-new `Membership` record for the member and updates that
member's own `membership_start`/`membership_end`/`membership_status`/`membership_plan`
fields (`accounts/user_views.py` `MemberPaymentView.post()`); `GET` lists those
`Membership` records. Because it's `Membership`, not `Payment`, being written, anything
created here will **not** show up via [`GET /payments/`](#get-payments) (that endpoint
queries `Payment` only) — use `GET /api/payments/?member_id=` below to see it instead.

### POST `/api/payments/`

Create a new `Membership` record for a member and update the member's own
membership-tracking fields to match it. The submitted `date` is validated (must be a
valid date) but is **not stored anywhere** — it has no corresponding column on either
`Membership` or `CustomUser`; the `date` field in the response below is actually just
`start_date` echoed back, not the submitted value.

**Permission:** `IsAdminOrGymOwner`. A gym owner may only target a member in their own
gym (`404` otherwise); an admin may target any member.

#### Request

| Field        | Type    | Required | Description                                                       |
| ------------ | ------- | -------- | --------------------------------------------------------------------|
| `member_id`  | UUID    | Yes      | Member's UUID                                                      |
| `date`       | string  | Yes      | Accepted and validated, but **not persisted** anywhere (see above) |
| `amount`     | decimal | Yes      | Written to the new `Membership.amount_paid` (min 0.01)             |
| `mode`       | string  | Yes      | `Cash` \| `Online` — written to `Membership.payment_mode`          |
| `start_date` | string  | Yes      | Membership start date                                              |
| `end_date`   | string  | Yes      | Membership end date (must be >= `start_date`)                      |
| `plan`       | string  | No       | Plan name (max 100 chars)                                          |

#### Response

`HTTP 201`. The response shape is the newly-created `Membership` record, reshaped:

| Field         | Type    | Description                                                       |
| ------------- | ------- | ---------------------------------------------------------------------|
| `uuid`        | UUID    | New `Membership` record's UUID                                    |
| `member_id`   | UUID    | Member UUID                                                        |
| `amount`      | decimal | Same value as `amount_paid` below (submitted `amount`)             |
| `amount_paid` | decimal | `Membership.amount_paid` — the submitted `amount`                  |
| `date`        | string  | **Not** the submitted `date` — this is `start_date` echoed back    |
| `start_date`  | string  | Membership start                                                   |
| `end_date`    | string  | Membership end                                                     |
| `mode`        | string  | `Membership.payment_mode` (`cash` \| `online`, lowercased)          |
| `plan`        | string  | Plan name                                                           |
| `status`      | string  | New membership's status — always `active`                           |

#### Example JSON Request

```json
{
  "member_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "date": "2026-06-30",
  "amount": "1500.00",
  "mode": "Cash",
  "start_date": "2026-07-01",
  "end_date": "2026-07-31",
  "plan": "Monthly"
}
```

#### Example JSON Response

```json
{
  "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "member_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "amount": "1500.00",
  "amount_paid": "1500.00",
  "date": "2026-07-01",
  "start_date": "2026-07-01",
  "end_date": "2026-07-31",
  "mode": "Cash",
  "plan": "Monthly",
  "status": "active"
}
```

---

### GET `/api/payments/?member_id={uuid}`

List `Membership` records (admin: all; gym owner: their gym's members only),
optionally filtered further by member.

**Pagination is optional.** Omitting `page_size` (or passing `page_size=0`, the
default) returns every matching `Membership` record in one response, with no
`count`/`next`/`previous` fields — this is the historical, still-default
behavior. Passing a positive `page_size` (max `100`, paired with `page`) switches
to the standard paginated envelope instead (`count`/`next`/`previous` populated,
`data` holding one page).

**Permission:** `IsAdminOrGymOwner`

**Query parameters:**

| Param       | Type    | Required | Description                                            |
| ----------- | ------- | -------- | ------------------------------------------------------- |
| `member_id` | UUID    | No       | Filter by member UUID                                  |
| `page`      | integer | No       | Page number (only used when `page_size` is set)         |
| `page_size` | integer | No       | Records per page, max `100`; `0`/omitted = return all   |

#### Example JSON Response

```json
[
  {
    "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "start_date": "2026-07-01",
    "end_date": "2026-07-31",
    "plan": "Monthly",
    "amount_paid": "1500.00",
    "payment_mode": "cash",
    "status": "active",
    "created_at": "2026-06-30T10:00:00Z",
    "updated_at": "2026-06-30T10:00:00Z"
  }
]
```

---

## 9. Attendance

Self-service attendance — a **member** or a **trainer** logs their own attendance using
their own auth token (there is no `member_id`/`user_id` in the request; the caller is
always the subject). A gym owner or admin cannot check anyone in or out; a gym owner can
only [list](#get-apiattendance) the records.

**Members and trainers are governed differently:**

- A **member**'s attendance is a single daily presence marker — **no check-out concept
  at all**. One check-in per calendar day (by the `timestamp` sent) is the entire record;
  `check_out`/`check_out_lat`/`check_out_lng`/`check_out_photo` stay `null` forever.
  `POST /api/attendance/checkout/` is `IsTrainer`-only and rejects a member with `403`.
  Checking in again the same day is rejected with `400`; a new day is a fresh check-in.
- A **trainer**'s attendance is a shift-style open/close pairing — check-in fails if
  they already have an unclosed (`check_out` is `null`) record; check-out fails if
  there's no open record to close.

**Geofence:** every check-in and check-out must be within **50 meters** of the caller's
gym (the `Gym` record their gym owner's account points to via `gym_details` — see
[Gym Master](#2-gym-master), which normally requires a location on every gym). Requests
outside that radius are declined with `400` and a message naming the actual distance.
If the caller isn't linked to a gym, or that gym has no registered location, the
request is declined with a distinct message (see the error table below) rather than
silently skipping the check.

**Photo:** required on both check-in and check-out for a **trainer** (`photo` field,
multipart upload); never used for a member — a member's request is
`lat`/`lng`/`timestamp` only, and a `photo` field on a member request is ignored.

### POST `/api/attendance/checkin/`

Check the authenticated member/trainer in.

**Permission:** `IsMember | IsTrainer`

#### Request

| Field       | Type     | Required     | Description                                                          |
| ----------- | -------- | ------------ | ------------------------------------------------------------------ |
| `timestamp` | datetime | Yes          | Check-in time (ISO-8601)                                          |
| `lat`       | decimal  | Yes          | Latitude (up to 9,6 precision)                                     |
| `lng`       | decimal  | Yes          | Longitude (up to 9,6 precision)                                    |
| `photo`     | string   | Trainer only | URL from `POST /api/upload-file/` — required for a trainer, ignored for a member |

#### Response

| Field             | Type             | Description                                        |
| ------------------ | ---------------- | ---------------------------------------------------- |
| `uuid`             | UUID             | Attendance record UUID                              |
| `user`             | UUID             | Member/trainer UUID (the caller)                     |
| `user_name`        | string           | Caller's full name                                   |
| `user_type`        | string           | `member` \| `trainer`                                |
| `check_in`         | datetime         | Check-in timestamp                                   |
| `check_out`        | datetime \| null | Check-out timestamp — always `null` for a member     |
| `check_in_lat`     | decimal          | Check-in latitude                                     |
| `check_in_lng`     | decimal          | Check-in longitude                                    |
| `check_out_lat`    | decimal \| null  | Check-out latitude — always `null` for a member       |
| `check_out_lng`    | decimal \| null  | Check-out longitude — always `null` for a member      |
| `check_in_photo`   | URL \| null      | Trainer check-in photo; always `null` for a member    |
| `check_out_photo`  | URL \| null      | Trainer check-out photo; always `null` for a member   |

#### Example JSON Request (member)

```json
{
  "timestamp": "2026-06-30T06:00:00Z",
  "lat": "19.075984",
  "lng": "72.877656"
}
```

#### Example JSON Response

```json
{
  "uuid": "e5f6a7b8-c9d0-1234-ef01-345678901234",
  "user": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "user_name": "Amit Verma",
  "user_type": "member",
  "check_in": "2026-06-30T06:00:00Z",
  "check_out": null,
  "check_in_lat": "19.075984",
  "check_in_lng": "72.877656",
  "check_out_lat": null,
  "check_out_lng": null,
  "check_in_photo": null,
  "check_out_photo": null
}
```

#### Error responses

| Status | When                                                    | Body                                                                                                  |
| ------ | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `400`  | Trainer omitted `photo`                                 | message: `"A photo is required for check-in."`                                                        |
| `400`  | Trainer already has an open check-in                    | message: `"You're already checked in."`                                                               |
| `400`  | Member already checked in on this `timestamp`'s date     | message: `"You've already checked in today."`                                                         |
| `400`  | `lat`/`lng` is more than 50m from the caller's gym       | message: `"You are <N>m away from your gym — check-in/out must be within 50m of the gym location."`  |
| `400`  | Caller's gym has no registered location                  | message: `"Your gym has no registered location. Contact your gym owner."`                             |

---

### POST `/api/attendance/checkout/`

Check the authenticated **trainer** out of their own currently-open attendance record —
no id needed in the request, the server finds it from `request.user`. **Trainer only —
a member calling this returns `403`; members have no check-out concept.**

**Permission:** `IsTrainer`

#### Request

Same shape as check-in: `timestamp`, `lat`, `lng`, and `photo` are all required.

#### Example JSON Request

```json
{
  "timestamp": "2026-06-30T07:30:00Z",
  "lat": "19.075984",
  "lng": "72.877656"
}
```

(`photo` omitted from the example above for brevity — it's a required field carrying the URL returned by `POST /api/upload-file/`.)

#### Example JSON Response

```json
{
  "uuid": "e5f6a7b8-c9d0-1234-ef01-345678901234",
  "user": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "user_name": "Priya Nair",
  "user_type": "trainer",
  "check_in": "2026-06-30T06:00:00Z",
  "check_out": "2026-06-30T07:30:00Z",
  "check_in_lat": "19.075984",
  "check_in_lng": "72.877656",
  "check_out_lat": "19.075984",
  "check_out_lng": "72.877656",
  "check_in_photo": "http://localhost:8000/media/attendance_photos/checkin.jpg",
  "check_out_photo": "http://localhost:8000/media/attendance_photos/checkout.jpg"
}
```

Error responses are the same shape as check-in (`photo` missing, geofence, gym has no
location), plus `400` / message `"No active check-in found."` if the trainer has
nothing open to close.

---

### GET `/api/attendance/`

List attendance records, optionally filtered by user and/or date.

**Permission:** `IsGymOwner | IsTrainer | IsMember` — a gym owner sees every attendance
record across their gym (members and trainers alike); a trainer or member only ever
sees their own.

**Pagination is optional.** Omitting `page_size` (or passing `page_size=0`, the
default) returns every matching record in one response, with no
`count`/`next`/`previous` fields — this is the historical, still-default behavior.
Passing a positive `page_size` (max `100`, paired with `page`) switches to the
standard paginated envelope instead (`count`/`next`/`previous` populated, `data`
holding one page).

**Query parameters:**

| Param       | Type    | Required | Description                                            |
| ----------- | ------- | -------- | ------------------------------------------------------- |
| `user_id`   | UUID    | No       | Filter by member/trainer UUID (gym owner)               |
| `date`      | string  | No       | Filter by date (`YYYY-MM-DD`)                            |
| `page`      | integer | No       | Page number (only used when `page_size` is set)         |
| `page_size` | integer | No       | Records per page, max `100`; `0`/omitted = return all   |

#### Example JSON Response

```json
[
  {
    "uuid": "e5f6a7b8-c9d0-1234-ef01-345678901234",
    "user": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "user_name": "Amit Verma",
    "user_type": "member",
    "check_in": "2026-06-30T06:00:00Z",
    "check_out": null,
    "check_in_lat": "19.075984",
    "check_in_lng": "72.877656",
    "check_out_lat": null,
    "check_out_lng": null,
    "check_in_photo": null,
    "check_out_photo": null
  }
]
```

---

## 10. Reports

Gym-owner-scoped reports are limited to the requesting gym owner's own gym; admin-scoped
reports (subscription expiry, revenue, storage, API traffic) are platform-wide.

### GET `/api/reports/inactive-members/`

Returns members whose last check-in is older than N days, or who have never checked in.
A gym owner sees every inactive member in their gym; a trainer sees only their own
assigned members.

**Permission:** `IsGymOwner | IsTrainer`

**Pagination is optional.** Omitting `page_size` (or passing `page_size=0`, the
default) returns every matching record in one response, with no
`count`/`next`/`previous` fields — this is the historical, still-default behavior.
Passing a positive `page_size` (max `100`, paired with `page`) switches to the
standard paginated envelope instead (`count`/`next`/`previous` populated, `data`
holding one page).

**Query parameters:**

| Param       | Type    | Required | Description                                            |
| ----------- | ------- | -------- | ------------------------------------------------------- |
| `days`      | integer | No       | Inactivity threshold in days (default: `7`)             |
| `page`      | integer | No       | Page number (only used when `page_size` is set)         |
| `page_size` | integer | No       | Records per page, max `100`; `0`/omitted = return all   |

#### Response

| Field           | Type           | Description                                 |
| --------------- | -------------- | ------------------------------------------- |
| `member_id`     | UUID           | Member UUID                                 |
| `name`          | string         | Full name                                   |
| `last_visit`    | string \| null | Last check-in date; `null` if never visited |
| `days_inactive` | integer        | Days since last visit; for a member who has **never** visited, this is not a sentinel — it's just the `?days=` threshold used for the query (default `7`) |

#### Example JSON Response

```json
[
  {
    "member_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Amit Verma",
    "last_visit": "2026-06-20",
    "days_inactive": 10
  },
  {
    "member_id": "c3d4e5f6-a7b8-1234-cdef-567890123456",
    "name": "Neha Singh",
    "last_visit": null,
    "days_inactive": 7
  }
]
```

---

### GET `/api/reports/trainer-workload/`

Returns each trainer in the gym along with the count of their active members.

**Permission:** `IsGymOwner`

**Pagination is optional.** Omitting `page_size` (or passing `page_size=0`, the
default) returns every matching record in one response, with no
`count`/`next`/`previous` fields — this is the historical, still-default behavior.
Passing a positive `page_size` (max `100`, paired with `page`) switches to the
standard paginated envelope instead (`count`/`next`/`previous` populated, `data`
holding one page).

**Query parameters:**

| Param       | Type    | Required | Description                                            |
| ----------- | ------- | -------- | ------------------------------------------------------- |
| `page`      | integer | No       | Page number (only used when `page_size` is set)         |
| `page_size` | integer | No       | Records per page, max `100`; `0`/omitted = return all   |

#### Response

| Field          | Type    | Description                       |
| -------------- | ------- | --------------------------------- |
| `trainer_id`   | UUID    | Trainer UUID                      |
| `name`         | string  | Full name                         |
| `member_count` | integer | Number of active members assigned |

#### Example JSON Response

```json
[
  {
    "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Priya Nair",
    "member_count": 12
  },
  {
    "trainer_id": "f6a7b8c9-d0e1-2345-f012-456789012345",
    "name": "Ravi Kumar",
    "member_count": 8
  }
]
```

---

### GET `/api/reports/membership-expiry/`

Returns members whose `membership_end` is on or before `today + X days` — there is
**no lower bound** on this filter (no `membership_end__gte` check), so it always
includes every member whose membership has already expired, no matter how long ago,
not just ones newly entering the X-day window.

**Permission:** `IsGymOwner`

**Pagination is optional.** Omitting `page_size` (or passing `page_size=0`, the
default) returns every matching record in one response, with no
`count`/`next`/`previous` fields — this is the historical, still-default behavior.
Passing a positive `page_size` (max `100`, paired with `page`) switches to the
standard paginated envelope instead (`count`/`next`/`previous` populated, `data`
holding one page).

**Query parameters:**

| Param       | Type    | Required | Description                                            |
| ----------- | ------- | -------- | ------------------------------------------------------- |
| `days`      | integer | No       | Lookahead window in days (default: `7`)                 |
| `page`      | integer | No       | Page number (only used when `page_size` is set)         |
| `page_size` | integer | No       | Records per page, max `100`; `0`/omitted = return all   |

#### Response

| Field         | Type    | Description                                     |
| ------------- | ------- | ----------------------------------------------- |
| `member_id`   | UUID    | Member UUID                                     |
| `name`        | string  | Full name                                       |
| `expiry_date` | string  | Membership end date                             |
| `days_left`   | integer | Days until expiry (negative if already expired) |

#### Example JSON Response

```json
[
  {
    "member_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Amit Verma",
    "expiry_date": "2026-07-03",
    "days_left": 3
  },
  {
    "member_id": "c3d4e5f6-a7b8-1234-cdef-567890123456",
    "name": "Neha Singh",
    "expiry_date": "2026-06-28",
    "days_left": -2
  }
]
```

---

### GET `/api/reports/gym-subscription-expiry/`

Admin-only. Returns gym **owner** accounts whose own platform subscription
(`membership_end`) is on or before `today + X days` — same as `membership-expiry`
above, there is **no lower bound**, so this always includes every gym owner whose
subscription has already expired, no matter how long ago. Distinct from
`membership-expiry` above, which is about **member** subscriptions within a single
gym.

**Permission:** `IsAdmin`

**Pagination is optional.** Omitting `page_size` (or passing `page_size=0`, the
default) returns every matching record in one response, with no
`count`/`next`/`previous` fields — this is the historical, still-default behavior.
Passing a positive `page_size` (max `100`, paired with `page`) switches to the
standard paginated envelope instead (`count`/`next`/`previous` populated, `data`
holding one page).

**Query parameters:**

| Param       | Type    | Required | Description                                            |
| ----------- | ------- | -------- | ------------------------------------------------------- |
| `days`      | integer | No       | Lookahead window in days (default: `7`)                 |
| `page`      | integer | No       | Page number (only used when `page_size` is set)         |
| `page_size` | integer | No       | Records per page, max `100`; `0`/omitted = return all   |

#### Response

| Field           | Type           | Description                                     |
| ---------------- | -------------- | ------------------------------------------------- |
| `gym_owner_id`  | UUID           | Gym owner UUID                                  |
| `name`          | string         | Full name                                       |
| `gym_name`      | string \| null | Name of the gym they own                        |
| `expiry_date`   | string         | Subscription end date                           |
| `days_left`     | integer        | Days until expiry (negative if already expired) |

#### Example JSON Response

```json
[
  {
    "gym_owner_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "name": "Raj Sharma",
    "gym_name": "Iron Paradise",
    "expiry_date": "2026-07-03",
    "days_left": 3
  }
]
```

---

### GET `/api/reports/revenue-summary/`

Aggregate revenue for the current calendar month, plus the payment-method breakdown for
the same period. Admin sees platform-wide revenue (gym-owner → platform payments); gym
owner sees their own gym's revenue (member → gym-owner payments) — same scoping as
[`GET /payments/`](#get-payments).

**Permission:** `IsAdmin | IsGymOwner`

#### Response

| Field                    | Type    | Description                                                          |
| ------------------------- | ------- | ----------------------------------------------------------------------- |
| `total_revenue`          | decimal | Sum of `paid` payments this calendar month                          |
| `monthly_growth_percent` | decimal | % change vs. last calendar month's total (`100.0` if last month was `0` and this month isn't; `0.0` if both are `0`) |
| `total_transactions`     | integer | Count of `paid` payments this calendar month                        |
| `pending_amount`         | decimal | Sum of all currently `pending` payments (not month-scoped — current outstanding total) |
| `method_breakdown`       | array   | `{method, amount}` per payment mode, this calendar month, paid only |

#### Example JSON Response

```json
{
  "total_revenue": "86400.00",
  "monthly_growth_percent": 12.4,
  "total_transactions": 42,
  "pending_amount": "3200.00",
  "method_breakdown": [
    { "method": "online", "amount": "54000.00" },
    { "method": "cash", "amount": "32400.00" }
  ]
}
```

---

### GET `/api/reports/storage-usage/`

Admin-only. Total size, in bytes, of everything under the server's media storage
(profile pictures, gym pictures, attendance photos, uploaded music files, etc.) —
computed by walking the media directory on request, not cached.

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "total_bytes": 40894627840
}
```

---

### GET `/api/reports/api-requests-today/`

Admin-only. Count of API requests received so far today (server local date), tracked by
a request-counting middleware. Excludes the Django admin UI, served media/static files,
and the API docs/schema routes — everything else counts, authenticated or not.

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "count": 12930
}
```

---

### GET `/api/reports/workout-backups-count/`

Admin-only. Count of distinct users who have synced their workout history to the server
via [`POST /api/backup/workouts/upload/`](#post-apibackupworkoutsupload).

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "count": 812
}
```

---

## 11. Backup / Sync

Offline-first sync endpoints using Last-Write-Wins conflict resolution on `updated_at`.

### POST `/api/backup/upload/`

Push client-side changes to the server. Conflicts are resolved by comparing `updated_at` timestamps — the server skips records where the incoming timestamp is older than or equal to the stored one.

**Permission:** `IsAdmin` | `IsGymOwner` | `IsTrainer`

#### Request

| Field              | Type   | Required | Description                                   |
| ------------------ | ------ | -------- | --------------------------------------------- |
| `user_id`          | UUID   | No       | Informational: the client user's UUID         |
| `changes`          | array  | Yes      | List of change objects                        |
| `changes[].model`  | string | Yes      | Model identifier e.g. `attendance.Attendance` |
| `changes[].action` | string | Yes      | `create` \| `update` \| `delete`              |
| `changes[].data`   | object | Yes      | Record payload (see fields below)             |

**Attendance data fields:**

| Field           | Type             | Description                         |
| --------------- | ---------------- | ----------------------------------- |
| `uuid`          | UUID             | Required for `update` and `delete`  |
| `user`          | UUID             | Member/trainer UUID — assign as `user_id` (see the request example below), not `user`; the view sets model fields directly from the payload, and `user` (the FK accessor) rejects a raw UUID string |
| `check_in`      | datetime         | Check-in timestamp                  |
| `check_out`     | datetime \| null | Check-out timestamp                 |
| `check_in_lat`  | decimal          | Check-in latitude — required on the model, never `null` |
| `check_in_lng`  | decimal          | Check-in longitude — required on the model, never `null` |
| `check_out_lat` | decimal \| null  | Check-out latitude                  |
| `check_out_lng` | decimal \| null  | Check-out longitude                 |
| `updated_at`    | datetime         | Client-side last modified timestamp |

#### Response

| Field             | Type    | Description                                 |
| ----------------- | ------- | ------------------------------------------- |
| `created`         | integer | Records created                             |
| `updated`         | integer | Records updated                             |
| `deleted`         | integer | Records deleted                             |
| `skipped`         | integer | Records skipped (conflict: server is newer) |
| `errors`          | array   | List of error objects — shape varies by failure kind, see below |

`errors[]` items are **not** uniformly shaped — the key set depends on which check
failed:

| Cause                                          | Item shape                                             |
| ----------------------------------------------- | -------------------------------------------------------- |
| Unknown/unsupported `model`                     | `{"model": "<model>", "error": "Unknown or unsupported model."}` (no `action` key) |
| Unknown `action` (not `create`/`update`/`delete`) | `{"action": "<action>", "error": "Unknown action."}` (no `model` key) |
| Exception while creating/updating/deleting       | `{"model": "<model>", "action": "<action>", "error": "<exception message>"}` (all three keys) |

#### Example JSON Request

`data.user` must be sent as `user_id` (the FK's raw column), not `user` — the view
assigns dict values straight onto model fields (`instance.user = data["user"]` /
`Model.objects.create(**data)`), and `Attendance.user` is a `ForeignKey`: assigning it
a plain string via the `user` accessor raises `ValueError`, whereas `user_id` accepts
the raw UUID directly.

```json
{
  "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "changes": [
    {
      "model": "attendance.Attendance",
      "action": "create",
      "data": {
        "user_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "check_in": "2026-06-30T06:00:00Z",
        "check_out": "2026-06-30T07:30:00Z",
        "check_in_lat": "19.075984",
        "check_in_lng": "72.877656",
        "check_out_lat": null,
        "check_out_lng": null,
        "updated_at": "2026-06-30T07:30:00Z"
      }
    }
  ]
}
```

#### Example JSON Response

```json
{
  "created": 1,
  "updated": 0,
  "deleted": 0,
  "skipped": 0,
  "errors": []
}
```

---

### GET `/api/backup/download/`

Pull server records that have changed since a given timestamp.

**Permission:** `IsAdmin` | `IsGymOwner` | `IsTrainer`

**Pagination is optional, and applies to `changes.attendance` specifically.**
Omitting `page_size` (or passing `page_size=0`, the default) returns every
matching attendance record as a bare array at `changes.attendance`, as shown
below — this is the historical, still-default behavior. Passing a positive
`page_size` (max `100`, paired with `page`) replaces that bare array with a
paginated envelope at the same key: `changes.attendance = {"count", "next",
"previous", "results"}`.

**Query parameters:**

| Param       | Type     | Required | Description                                                 |
| ----------- | -------- | -------- | ------------------------------------------------------------ |
| `user_id`   | UUID     | No       | Filter records by member UUID                                |
| `since`     | datetime | No       | ISO-8601 timestamp; returns records updated after this time  |
| `page`      | integer  | No       | Page number (only used when `page_size` is set)              |
| `page_size` | integer  | No       | Records per page, max `100`; `0`/omitted = return all        |

#### Response

| Field                | Type            | Description                                                             |
| -------------------- | --------------- | ------------------------------------------------------------------------ |
| `changes.attendance` | array \| object | List of attendance records updated since `since`, or a paginated envelope if `page_size` was passed |

#### Example JSON Response

```json
{
  "changes": {
    "attendance": [
      {
        "uuid": "e5f6a7b8-c9d0-1234-ef01-345678901234",
        "user": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "check_in": "2026-06-30T06:00:00Z",
        "check_out": "2026-06-30T07:30:00Z",
        "check_in_lat": "19.075984",
        "check_in_lng": "72.877656",
        "check_out_lat": null,
        "check_out_lng": null
      }
    ]
  }
}
```

---

### POST `/api/backup/workouts/upload/`

Replaces the authenticated user's **entire** server-side workout history with what's in
the request body — this is a whole-history replace, not a per-record merge like
`/api/backup/upload/` above. The local app never deletes old sessions (it only
accumulates), so each sync's payload already contains everything the user has ever
logged; replacing avoids double-counting a session that was already synced in a
previous call. Mirrors the local app's `workout_sessions` / `session_exercises` /
`exercise_sets` / `session_rest_breaks` tables.

**Permission:** Authenticated (any role)

#### Request

| Field                          | Type            | Required | Description                                    |
| ------------------------------- | --------------- | -------- | ------------------------------------------------- |
| `sessions`                     | array           | Yes      | Full list of the user's workout sessions          |
| `sessions[].session_date`      | string          | Yes      | `YYYY-MM-DD`                                      |
| `sessions[].duration_minutes`  | integer         | No       | Default `0`                                       |
| `sessions[].notes`             | string \| null  | No       |                                                    |
| `sessions[].calories_burned`   | decimal \| null | No       |                                                    |
| `sessions[].is_rest_day`       | boolean         | No       | Default `false`                                   |
| `sessions[].exercises`         | array           | No       | See below                                         |
| `sessions[].rest_breaks`       | array           | No       | `{duration_minutes, sort_index}` objects          |
| `exercises[].exercise_name`    | string          | Yes      |                                                    |
| `exercises[].body_part`        | string \| null  | No       |                                                    |
| `exercises[].muscle`           | string \| null  | No       |                                                    |
| `exercises[].is_unilateral`    | boolean         | No       | Default `false`                                   |
| `exercises[].set_type`         | string          | No       | Default `"normal"`                                |
| `exercises[].superset_group`   | integer \| null | No       |                                                    |
| `exercises[].sets`             | array           | No       | See below                                         |
| `sets[].set_number`            | integer         | No       | Defaults to 1-based position in the array         |
| `sets[].reps`                  | integer \| null | No       |                                                    |
| `sets[].weight_kg`             | decimal \| null | No       |                                                    |
| `sets[].duration_seconds`      | integer \| null | No       |                                                    |
| `sets[].speed_kmh`             | decimal \| null | No       |                                                    |

#### Response

| Field             | Type    | Description                                    |
| ------------------ | ------- | ------------------------------------------------- |
| `synced_sessions` | integer | Count of sessions now stored for this user (post-replace) |

#### Example JSON Request

```json
{
  "sessions": [
    {
      "session_date": "2026-01-15",
      "duration_minutes": 45,
      "notes": "Leg day",
      "calories_burned": 320.5,
      "is_rest_day": false,
      "exercises": [
        {
          "exercise_name": "Barbell Squat",
          "body_part": "Legs",
          "muscle": "Quads",
          "is_unilateral": false,
          "set_type": "normal",
          "sets": [
            { "set_number": 1, "reps": 10, "weight_kg": 60.0 },
            { "set_number": 2, "reps": 8, "weight_kg": 65.0 }
          ]
        }
      ],
      "rest_breaks": [{ "duration_minutes": 2, "sort_index": 0 }]
    }
  ]
}
```

#### Example JSON Response

```json
{
  "synced_sessions": 1
}
```

---

## 12. Utility

### HEAD `/api/health/`

Health check — returns HTTP 200 with no body. Use for liveness probes.

**Permission:** Public

**Response:** `HTTP 200 OK` (empty body)

---

### GET `/api/my-ip/`

Returns IP geolocation, browser, OS, and device information for the requesting client. Pass `?ip=` to look up a specific IP address instead.

**Permission:** Public

**Query parameters:**

| Param | Type   | Required | Description                                   |
| ----- | ------ | -------- | --------------------------------------------- |
| `ip`  | string | No       | IP address to look up (defaults to client IP) |

#### Response

| Field                | Type    | Description                               |
| -------------------- | ------- | ----------------------------------------- |
| `ip`                 | string  | IP address                                |
| `location.country`   | string  | Country name                              |
| `location.city`      | string  | City name                                 |
| `location.region`    | string  | Region/state                              |
| `location.latitude`  | float   | Latitude                                  |
| `location.longitude` | float   | Longitude                                 |
| `browser.name`       | string  | Browser name                              |
| `browser.version`    | string  | Browser version                           |
| `os.name`            | string  | OS name                                   |
| `os.version`         | string  | OS version                                |
| `device.type`        | string  | `mobile` \| `tablet` \| `pc` \| `unknown` |
| `device.brand`       | string  | Device brand                              |
| `device.model`       | string  | Device model                              |
| `is_bot`             | boolean | Whether the client appears to be a bot    |

#### Example JSON Response

```json
{
  "ip": "103.21.244.0",
  "location": {
    "country": "India",
    "city": "Mumbai",
    "region": "Maharashtra",
    "latitude": 19.076,
    "longitude": 72.8777
  },
  "browser": {
    "name": "Chrome",
    "version": "125.0"
  },
  "os": {
    "name": "Android",
    "version": "14"
  },
  "device": {
    "type": "mobile",
    "brand": "Samsung",
    "model": "Galaxy S24"
  },
  "is_bot": false
}
```

**Error Responses:**

| Status            | When                                               |
| ----------------- | -------------------------------------------------- |
| `400 Bad Request` | Private/non-routable IP or geolocation unavailable |
| `404 Not Found`   | No location data found for the given IP            |

---

### POST `/api/upload-file/`

Uploads an image and returns its URL. This is the generic first step for every image field in the API (`profile_picture`, `gym_picture`, attendance `photo`, music `thumb`/`icon`/`cover`, etc.) — those fields no longer accept a raw multipart file directly; instead, upload the file here first, then send the returned `url` as a plain string in the JSON (or mixed multipart) body of the actual create/update request. A field's own validation only checks that the URL points at a file that actually exists in this server's media storage — so an unchanged value (e.g. re-sending a `profile_picture` that was already set) always round-trips successfully instead of failing.

**Permission:** Any authenticated user

**Content-Type:** `multipart/form-data`

#### Request

| Field  | Type | Required | Description                                                                  |
| ------ | ---- | -------- | ----------------------------------------------------------------------------- |
| `file` | file | Yes      | Image to upload. Allowed types: `jpg`, `jpeg`, `png`, `webp`. Max size: 5MB.  |

#### Example JSON Response

```json
{
  "url": "http://<host>/media/uploads/1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b.jpg"
}
```

**Error Responses:**

| Status            | When                                              |
| ----------------- | -------------------------------------------------- |
| `400 Bad Request` | Missing file, unsupported type, or file over 5MB   |

---

## 13. Music (Playlists & Songs)

Admin-managed music catalogue served to the Flutter app. The catalogue is split
into two tiers, and the backend owns the whole integer id space (`songs` `1..165`,
`playlists` `1..9` are already taken), so admin-created rows continue from id
`166` / `10` and never collide with the app's offline bundle.

| Tier        | Playlists                                                                                                            | Songs     | Media lives           |
| ----------- | -------------------------------------------------------------------------------------------------------------------- | --------- | --------------------- |
| **Bundled** | `1` Devotional, `2` Maharaj, `3` No Excuses                                                                          | `1..53`   | Inside the app bundle |
| **Remote**  | `4` Punjabis, `5` Bad\*ss BGMs, `6` Sambata Don, `7` Dr. Divine, `8` Ustad Nusrat Fateh Ali Khan, `9` Aditya Rikhari | `54..165` | Server `MEDIA_ROOT`   |

Every item carries `is_remote`:

- `is_remote = false` — a bundled item; its `thumb`/`asset`/`icon`/`cover` are the
  app's local `assets/...` paths, shipped inside the app.
- `is_remote = true` — a streamed item; its media fields are absolute download
  URLs (`http://<host>/media/...`). The app shows a download button for these.
  This covers both playlists `4..9` and anything an admin adds later.

The app's bundled `songs.json` / `playlists.json` contain **only** the bundled tier,
so the remote tier is served exclusively by these endpoints — the app merges the two
and bundled ids win on collision.

Media: `thumb`/`icon`/`cover` are images — upload them via `POST /api/upload-file/`
first and send the returned URL as a plain string field (see [Utility](#12-utility)).
`asset` (song audio) is still a real file upload and must be `.opus`; create/update
requests stay `multipart/form-data` for that reason, mixing the `asset` file part
with the `thumb`/`icon`/`cover` string fields in the same request. `color` is a hex
string without `#` (e.g. `520102`).

### GET `/api/music/songs/`

List the full song catalogue (all 165 seeded songs plus anything an admin added).

**Permission:** Any authenticated user

**Pagination is optional.** Omitting `page_size` (or passing `page_size=0`, the
default) returns the complete catalogue in `data`, matching the app's
`songs.json` shape plus `is_remote` — this is the historical, still-default
behavior (and what the Flutter app relies on). Passing a positive `page_size`
(max `100`, paired with `page`) switches to the standard paginated envelope
instead (`count`/`next`/`previous` populated, `data` holding one page).

**Query parameters:**

| Param       | Type    | Required | Description                                            |
| ----------- | ------- | -------- | ------------------------------------------------------- |
| `page`      | integer | No       | Page number (only used when `page_size` is set)         |
| `page_size` | integer | No       | Records per page, max `100`; `0`/omitted = return all   |

#### Response (`data[]`)

| Field       | Type    | Description                                                                                  |
| ----------- | ------- | -------------------------------------------------------------------------------------------- |
| `id`        | integer | Song id (`1..53` bundled, `54..165` remote, `166+` admin-added)                              |
| `title`     | string  | Song title                                                                                   |
| `artist`    | string  | Artist name                                                                                  |
| `thumb`     | string  | `assets/...png` path (bundled) or absolute URL (remote); `null` if the song has no thumbnail |
| `asset`     | string  | `assets/...opus` path (bundled) or absolute URL (remote)                                     |
| `duration`  | integer | Length in seconds                                                                            |
| `is_remote` | boolean | `false` = bundled, `true` = streamed / downloadable                                          |

A `null` `thumb` is expected for a handful of remote songs that ship without artwork
(ids `94` and `112..122`); the app falls back to its own `default.png`.

#### Example JSON Response

```json
[
  {
    "id": 16,
    "title": "Aarambh Hai Prachand",
    "artist": "Piyush Mishra",
    "thumb": "assets/audio-thumb/aarambh_hai_prachand.png",
    "asset": "assets/audio-opus/aarambh_hai_prachand.opus",
    "duration": 298,
    "is_remote": false
  },
  {
    "id": 133,
    "title": "3:59 AM",
    "artist": "Divine",
    "thumb": "http://<host>/media/music/thumbs/3_59_am.png",
    "asset": "http://<host>/media/music/audio/3_59_am.opus",
    "duration": 286,
    "is_remote": true
  },
  {
    "id": 112,
    "title": "Chaos In Khansaar",
    "artist": "Ravi Basrur",
    "thumb": null,
    "asset": "http://<host>/media/music/audio/chaos_in_khansaar.opus",
    "duration": 76,
    "is_remote": true
  }
]
```

---

### POST `/api/music/songs/`

Create a new song. The new `id` is assigned automatically (continues the sequence).

**Permission:** `IsAdmin` · **Content-Type:** `multipart/form-data`

#### Request

| Field      | Type    | Required | Description                     |
| ---------- | ------- | -------- | ------------------------------- |
| `title`    | string  | Yes      | Song title                                                          |
| `artist`   | string  | No       | Artist name                                                         |
| `duration` | integer | No       | Length in seconds (client-sent); `Song.duration` defaults to `0` — omitting the field silently stores `0`, it isn't computed from `asset` |
| `thumb`    | string  | Yes      | URL from `POST /api/upload-file/`                                   |
| `asset`    | file    | Yes      | `.opus` audio file                                                  |

#### Example JSON Response

```json
{
  "id": 141,
  "title": "New Track",
  "artist": "New Artist",
  "thumb": "http://<host>/media/music/thumbs/new_track.png",
  "asset": "http://<host>/media/music/audio/new_track.opus",
  "duration": 210,
  "is_remote": true
}
```

**Error Responses:**

| Status            | When                                                                        |
| ----------------- | ---------------------------------------------------------------------------- |
| `400 Bad Request` | Missing required field, `thumb` isn't a valid uploaded-file URL, or `asset` not `.opus` |
| `403 Forbidden`   | Caller is not an admin                                                     |

---

### GET `/api/music/songs/{id}/`

Retrieve a single song. **Permission:** Any authenticated user. Response shape is one song object (as above).

---

### PUT `/api/music/songs/{id}/`

Full replace of a song. **Permission:** `IsAdmin` · `multipart/form-data`. Same fields as `POST`. Returns the updated song object.

---

### POST `/api/music/songs/{id}/update/`

Partial update of a song (POST-not-PATCH convention). **Permission:** `IsAdmin` · `multipart/form-data`. Any subset of the create fields. Returns the updated song object.

---

### DELETE `/api/music/songs/{id}/`

Soft-delete a song (hidden from lists; id is not reused). **Permission:** `IsAdmin`. Returns `HTTP 204 No Content`.

---

### GET `/api/music/playlists/`

List the full playlist catalogue (all 9 seeded playlists plus anything an admin
added).

**Permission:** Any authenticated user

**Pagination is optional.** Omitting `page_size` (or passing `page_size=0`, the
default) returns the complete catalogue in `data`, matching the app's
`playlists.json` shape plus `is_remote` — this is the historical, still-default
behavior (and what the Flutter app relies on). Passing a positive `page_size`
(max `100`, paired with `page`) switches to the standard paginated envelope
instead (`count`/`next`/`previous` populated, `data` holding one page).

**Query parameters:**

| Param       | Type    | Required | Description                                            |
| ----------- | ------- | -------- | ------------------------------------------------------- |
| `page`      | integer | No       | Page number (only used when `page_size` is set)         |
| `page_size` | integer | No       | Records per page, max `100`; `0`/omitted = return all   |

#### Response (`data[]`)

| Field       | Type             | Description                                                    |
| ----------- | ---------------- | -------------------------------------------------------------- |
| `id`        | integer          | Playlist id (`1..3` bundled, `4..9` remote, `10+` admin-added) |
| `title`     | string           | Playlist title                                                 |
| `icon`      | string \| null   | `assets/...png` path (bundled) or absolute URL (remote); `null` if a bundled playlist has no icon (same fallback pattern as `Song.thumb`, see above) |
| `cover`     | string \| null   | `assets/...png` path (bundled) or absolute URL (remote); `null` if a bundled playlist has no cover |
| `color`     | string           | Hex color without `#` (e.g. `520102`)                          |
| `song_ids`  | array of integer | Ordered song ids in the playlist                               |
| `is_remote` | boolean          | `false` = bundled, `true` = streamed                           |

#### Example JSON Response

```json
[
  {
    "id": 3,
    "title": "No Excuses",
    "icon": "assets/playlist-thumb/no_excuses_icon.png",
    "cover": "assets/playlist-thumb/no_excuses.png",
    "color": "C58B12",
    "song_ids": [50, 51, 52, 53],
    "is_remote": false
  },
  {
    "id": 6,
    "title": "Sambata Don",
    "icon": "http://<host>/media/music/icons/sambata_icon.png",
    "cover": "http://<host>/media/music/covers/sambata.png",
    "color": "4B1D5A",
    "song_ids": [125, 126, 127, 128, 129, 130, 131, 132],
    "is_remote": true
  }
]
```

---

### POST `/api/music/playlists/`

Create a new playlist. The new `id` is assigned automatically. `song_ids` is
optional — a playlist can be created empty and have songs added later; when
provided it may mix bundled and admin-added song ids, and ordering is preserved.

**Permission:** `IsAdmin` · **Content-Type:** `multipart/form-data`

#### Request

| Field      | Type             | Required | Description                                                                             |
| ---------- | ---------------- | -------- | --------------------------------------------------------------------------------------- |
| `title`    | string           | Yes      | Playlist title                                                                          |
| `icon`     | string           | Yes      | URL from `POST /api/upload-file/`                                                       |
| `cover`    | string           | Yes      | URL from `POST /api/upload-file/`                                                       |
| `color`    | string           | No       | Hex color without `#` (e.g. `520102`)                                                   |
| `song_ids` | array of integer | No       | Ordered list of existing song ids (bundled or remote); omit to create an empty playlist |

For `multipart/form-data`, send `song_ids` as repeated fields (`song_ids=1`, `song_ids=5`, …).

#### Example JSON Response

```json
{
  "id": 8,
  "title": "My Mix",
  "icon": "http://<host>/media/music/icons/my_mix_icon.png",
  "cover": "http://<host>/media/music/covers/my_mix.png",
  "color": "6A1B9A",
  "song_ids": [1, 5, 141],
  "is_remote": true
}
```

**Error Responses:**

| Status            | When                                                                               |
| ----------------- | ---------------------------------------------------------------------------------- |
| `400 Bad Request` | Missing field, `icon`/`cover` not a valid uploaded-file URL, or `song_ids` referencing an unknown/deleted song |
| `403 Forbidden`   | Caller is not an admin                                                             |

---

### GET `/api/music/playlists/{id}/`

Retrieve a single playlist. **Permission:** Any authenticated user. Response is one playlist object (as above).

---

### PUT `/api/music/playlists/{id}/`

Full replace of a playlist. **Permission:** `IsAdmin` · `multipart/form-data`. Same fields as `POST`; if `song_ids` is provided it replaces the full ordered set — `song_ids` is optional even on `PUT` (the serializer marks it `required=False`), and omitting it entirely leaves the playlist's existing songs untouched rather than clearing them. Returns the updated playlist object.

---

### POST `/api/music/playlists/{id}/update/`

Partial update of a playlist (POST-not-PATCH convention). **Permission:** `IsAdmin` · `multipart/form-data`. Any subset of the create fields; if `song_ids` is provided it replaces the full ordered set. Returns the updated playlist object.

---

### DELETE `/api/music/playlists/{id}/`

Soft-delete a playlist (hidden from lists; id is not reused). **Permission:** `IsAdmin`. Returns `HTTP 204 No Content`.

---

## Schema & Documentation

| Endpoint       | Description               |
| -------------- | ------------------------- |
| `GET /schema/` | OpenAPI 3.0 schema (JSON) |
| `GET /docs/`   | Swagger UI                |
