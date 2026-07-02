# Fit&Fuel API Documentation

**Version:** Phase 1  
**Base URL:** `http://<host>/`  
**Authentication:** JWT Bearer Token — include `Authorization: Bearer <access_token>` on all protected endpoints.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Gym Master](#2-gym-master)
3. [User Management](#3-user-management)
4. [Trainer Panel](#4-trainer-panel)
5. [Member Panel](#5-member-panel)
6. [Memberships](#6-memberships)
7. [Payments (Legacy)](#7-payments-legacy)
8. [Member Payments (Phase 3)](#8-member-payments-phase-3)
9. [Attendance](#9-attendance)
10. [Reports](#10-reports)
11. [Backup / Sync](#11-backup--sync)
12. [Utility](#12-utility)

---

## Permission Roles

| Role                  | Condition                             |
| --------------------- | ------------------------------------- |
| `IsAdmin`             | `user_type == admin`                  |
| `IsGymOwner`          | `user_type == gym_owner`              |
| `IsTrainer`           | `user_type == trainer`                |
| `IsMember`            | `user_type == member`                 |
| `IsAdminOrGymOwner`   | `user_type` in `admin`, `gym_owner`   |
| `IsGymOwnerOrTrainer` | `user_type` in `gym_owner`, `trainer` |

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

```json
{
  "detail": "Logged out successfully."
}
```

---

### GET `/auth/profile/`

Returns the full profile of the currently authenticated user.

**Permission:** Authenticated

#### Response

| Field             | Type            | Description                                        |
| ----------------- | --------------- | -------------------------------------------------- |
| `uuid`            | UUID            | User identifier                                    |
| `phone_number`    | string          | Phone number                                       |
| `first_name`      | string          | First name                                         |
| `last_name`       | string          | Last name                                          |
| `date_of_birth`   | string \| null  | Date of birth                                      |
| `age`             | integer \| null | Computed age                                       |
| `gender`          | string          | `male` \| `female` \| `other`                      |
| `profile_picture` | URL \| null     | Profile image URL                                  |
| `user_type`       | string          | `admin` \| `gym_owner` \| `trainer` \| `member`    |
| `status`          | string          | `active` \| `disabled` \| `suspended` \| `deleted` |
| `gym_id`          | UUID \| null    | Associated gym                                     |
| `trainer_id`      | UUID \| null    | Assigned trainer                                   |
| `created_at`      | datetime        | Account creation timestamp                         |

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
  "user_type": "gym_owner",
  "status": "active",
  "gym_id": null,
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

```json
{
  "detail": "Password updated successfully."
}
```

---

## 2. Gym Master

Master record of gym names, referenced by `gym_uuid` on gym-owner accounts (see [User Management](#3-user-management)). Endpoints under `/gyms/` support pagination, search, and ordering.

**Permission:** `IsAdmin` for create/update/delete. Any authenticated user (`admin`, `gym_owner`, `trainer`, `member`) can list/retrieve.

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
      "name": "Iron Paradise"
    }
  ]
}
```

---

### POST `/gyms/`

Create a new gym master record.

**Permission:** `IsAdmin`

#### Request

| Field  | Type   | Required | Description |
| ------ | ------ | -------- | ----------- |
| `name` | string | Yes      | Gym name    |

#### Example JSON Request

```json
{
  "name": "Iron Paradise"
}
```

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Iron Paradise"
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
  "name": "Iron Paradise"
}
```

---

### PUT `/gyms/{uuid}/`

Full update of a gym record.

**Permission:** `IsAdmin`

#### Example JSON Request

```json
{
  "name": "Renamed Gym"
}
```

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Renamed Gym"
}
```

---

### POST `/gyms/{uuid}/update/`

Partial update of a gym record.

**Permission:** `IsAdmin`

#### Example JSON Request

```json
{
  "name": "Renamed Gym"
}
```

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Renamed Gym"
}
```

---

### DELETE `/gyms/{uuid}/`

Soft-delete a gym record (sets `is_deleted = true`).

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "detail": "Deleted successfully."
}
```

---

### POST `/gyms/{uuid}/enable/`

Re-enable a soft-deleted gym record (sets `is_deleted = false`).

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "name": "Iron Paradise"
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

List all gym owners. Supports filtering, search, and ordering.

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

#### Request

| Field             | Type           | Required | Description                                                                                           |
| ----------------- | -------------- | -------- | ----------------------------------------------------------------------------------------------------- |
| `phone_number`    | string         | Yes      | Must be unique, max 15 chars                                                                          |
| `password`        | string         | Yes      | Strong password (min 8 chars, mixed case, digit, special char)                                        |
| `first_name`      | string         | Yes      | First name                                                                                            |
| `last_name`       | string         | Yes      | Last name                                                                                             |
| `date_of_birth`   | string \| null | No       | Format: `YYYY-MM-DD`                                                                                  |
| `gender`          | string         | No       | `male` \| `female` \| `other`                                                                         |
| `profile_picture` | file \| null   | No       | Image upload                                                                                          |
| `gym_name`        | string         | Yes      | Name of the gym owned by this account; stored in a separate `Gym` master record                       |
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

Retrieve a single gym owner by UUID. The response includes a `trainers` list — every active trainer assigned to this gym owner's gym.

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

Uses the same writable fields as `GymOwnerDetailSerializer` — `phone_number`, `first_name`, `last_name`, `date_of_birth`, `gender`, `profile_picture`, `status`, `trainer_limit`, `membership_start`, `membership_end` (all required for PUT). Note this is a different serializer than `POST /users/gym-owners/`: `gym_name` and `membership` are create-only and cannot be changed via PUT/`update/`.

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
  "membership_start": "2026-01-15",
  "membership_end": "2026-02-14",
  "created_at": "2025-01-10T08:30:00Z"
}
```

---

### DELETE `/users/gym-owners/{uuid}/`

Soft-delete a gym owner (sets `is_deleted = true`).

**Permission:** `IsAdmin`

#### Example JSON Response

```json
{
  "detail": "Deleted successfully."
}
```

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
  "membership_start": "2026-01-15",
  "membership_end": "2026-02-14",
  "created_at": "2025-01-10T08:30:00Z"
}
```

---

### GET `/users/trainers/`

List all trainers belonging to the requesting gym owner's gym.

**Permission:** `IsGymOwner`  
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

#### Request

| Field             | Type           | Required | Description                   |
| ----------------- | -------------- | -------- | ----------------------------- |
| `phone_number`    | string         | Yes      | Must be unique, max 15 chars  |
| `password`        | string         | Yes      | Strong password               |
| `first_name`      | string         | Yes      | First name                    |
| `last_name`       | string         | Yes      | Last name                     |
| `date_of_birth`   | string \| null | No       | Format: `YYYY-MM-DD`          |
| `gender`          | string         | No       | `male` \| `female` \| `other` |
| `profile_picture` | file \| null   | No       | Image upload                  |

#### Example JSON Request

```json
{
  "phone_number": "9000000001",
  "password": "Trainer@123",
  "first_name": "Priya",
  "last_name": "Nair",
  "date_of_birth": "1995-07-12",
  "gender": "female"
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
  "created_at": "2026-06-30T10:00:00Z"
}
```

---

### GET `/users/trainers/{uuid}/`

Retrieve a trainer by UUID.

**Permission:** `IsGymOwner`

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

**Permission:** `IsGymOwner`

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

**Permission:** `IsGymOwner`

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

**Permission:** `IsGymOwner`

#### Example JSON Response

```json
{
  "detail": "Deleted successfully."
}
```

---

### POST `/users/trainers/{uuid}/disable/`

Disable a trainer account.

**Permission:** `IsGymOwner`

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

**Permission:** `IsGymOwner`

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

List all members belonging to the requesting gym owner's gym.

**Permission:** `IsGymOwner`  
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

#### Request

| Field             | Type           | Required | Description                       |
| ----------------- | -------------- | -------- | --------------------------------- |
| `phone_number`    | string         | Yes      | Must be unique, max 15 chars      |
| `password`        | string         | Yes      | Strong password                   |
| `first_name`      | string         | Yes      | First name                        |
| `last_name`       | string         | Yes      | Last name                         |
| `date_of_birth`   | string \| null | No       | Format: `YYYY-MM-DD`              |
| `gender`          | string         | No       | `male` \| `female` \| `other`     |
| `profile_picture` | file \| null   | No       | Image upload                      |
| `trainer_uuid`    | UUID \| null   | No       | UUID of a trainer in the same gym |

#### Example JSON Request

```json
{
  "phone_number": "9111111111",
  "password": "Member@123",
  "first_name": "Amit",
  "last_name": "Verma",
  "date_of_birth": "2000-11-05",
  "gender": "male",
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
  "created_at": "2026-06-30T10:00:00Z"
}
```

---

### GET `/users/members/{uuid}/`

Retrieve a member by UUID.

**Permission:** `IsGymOwner`

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

**Permission:** `IsGymOwner`

#### Example JSON Request

```json
{
  "first_name": "Amitabh",
  "last_name": "Verma",
  "gender": "male",
  "status": "active"
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

**Permission:** `IsGymOwner`

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

**Permission:** `IsGymOwner`

#### Example JSON Response

```json
{
  "detail": "Deleted successfully."
}
```

---

### POST `/users/members/{uuid}/disable/`

Disable a member account.

**Permission:** `IsGymOwner`

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

**Permission:** `IsGymOwner`

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

**Permission:** `IsGymOwner`

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

| Field             | Type        | Description                   |
| ----------------- | ----------- | ----------------------------- |
| `uuid`            | UUID        | Member identifier (read-only) |
| `phone_number`    | string      | Phone number (read-only)      |
| `first_name`      | string      | First name                    |
| `last_name`       | string      | Last name                     |
| `profile_picture` | URL \| null | Profile image URL             |
| `date_of_birth`   | string      | Date of birth (read-only)     |
| `age`             | integer     | Computed age (read-only)      |
| `gender`          | string      | `male` \| `female` \| `other` |

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
  "gender": "male"
}
```

---

### POST `/member/profile/`

Update the authenticated member's own profile. Only editable fields can be changed.

**Permission:** `IsMember`

#### Request

| Field             | Type         | Required | Description                   |
| ----------------- | ------------ | -------- | ----------------------------- |
| `first_name`      | string       | No       | First name                    |
| `last_name`       | string       | No       | Last name                     |
| `profile_picture` | file \| null | No       | Image upload                  |
| `gender`          | string       | No       | `male` \| `female` \| `other` |

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
  "gender": "male"
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

#### Example JSON Response

```json
{
  "detail": "Deleted successfully."
}
```

---

## 7. Payments (Legacy)

### GET `/payments/`

List payment records. Optionally filter by member using `?member=<uuid>`.

**Permission:** `IsAdminOrGymOwner`  
**Filter fields:** `mode`, `membership`  
**Query param:** `member` (UUID)  
**Ordering fields:** `paid_on`, `created_at`

#### Example JSON Response

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "uuid": "d4e5f6a7-b8c9-0123-def0-234567890123",
      "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "amount": "1500.00",
      "mode": "cash",
      "paid_on": "2026-06-01T08:00:00Z",
      "created_at": "2026-06-01T08:00:00Z"
    }
  ]
}
```

---

### POST `/payments/`

Record a payment against an existing membership.

**Permission:** `IsAdminOrGymOwner`

#### Request

| Field        | Type     | Required | Description                   |
| ------------ | -------- | -------- | ----------------------------- |
| `membership` | UUID     | Yes      | UUID of the linked membership |
| `amount`     | decimal  | Yes      | Payment amount (must be > 0)  |
| `mode`       | string   | Yes      | `cash` \| `online`            |
| `paid_on`    | datetime | Yes      | Payment timestamp             |

#### Example JSON Request

```json
{
  "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "amount": "1500.00",
  "mode": "cash",
  "paid_on": "2026-06-01T08:00:00Z"
}
```

#### Example JSON Response

```json
{
  "uuid": "d4e5f6a7-b8c9-0123-def0-234567890123",
  "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "amount": "1500.00",
  "mode": "cash",
  "paid_on": "2026-06-01T08:00:00Z",
  "created_at": "2026-06-30T10:00:00Z"
}
```

---

### GET `/payments/{uuid}/`

Retrieve a specific payment record.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Response

```json
{
  "uuid": "d4e5f6a7-b8c9-0123-def0-234567890123",
  "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "amount": "1500.00",
  "mode": "cash",
  "paid_on": "2026-06-01T08:00:00Z",
  "created_at": "2026-06-01T08:00:00Z"
}
```

---

### PUT `/payments/{uuid}/`

Full update of a payment record.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Request

```json
{
  "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "amount": "1600.00",
  "mode": "online",
  "paid_on": "2026-06-02T10:00:00Z"
}
```

#### Example JSON Response

```json
{
  "uuid": "d4e5f6a7-b8c9-0123-def0-234567890123",
  "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "amount": "1600.00",
  "mode": "online",
  "paid_on": "2026-06-02T10:00:00Z",
  "created_at": "2026-06-01T08:00:00Z"
}
```

---

### POST `/payments/{uuid}/update/`

Partial update of a payment record.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Request

```json
{
  "mode": "online"
}
```

#### Example JSON Response

```json
{
  "uuid": "d4e5f6a7-b8c9-0123-def0-234567890123",
  "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "amount": "1500.00",
  "mode": "online",
  "paid_on": "2026-06-01T08:00:00Z",
  "created_at": "2026-06-01T08:00:00Z"
}
```

---

### DELETE `/payments/{uuid}/`

Soft-delete a payment record.

**Permission:** `IsAdminOrGymOwner`

#### Example JSON Response

```json
{
  "detail": "Deleted successfully."
}
```

---

## 8. Member Payments (Phase 3)

A combined endpoint that creates or updates a membership record and records the payment in one operation.

### POST `/api/payments/`

Record a membership payment and update the member's membership dates atomically.

**Permission:** `IsAdminOrGymOwner`

#### Request

| Field        | Type    | Required | Description                                   |
| ------------ | ------- | -------- | --------------------------------------------- |
| `member_id`  | UUID    | Yes      | Member's UUID                                 |
| `date`       | string  | Yes      | Payment date                                  |
| `amount`     | decimal | Yes      | Amount paid (min 0.01)                        |
| `mode`       | string  | Yes      | `Cash` \| `Online`                            |
| `start_date` | string  | Yes      | Membership start date                         |
| `end_date`   | string  | Yes      | Membership end date (must be >= `start_date`) |
| `plan`       | string  | No       | Plan name (max 100 chars)                     |

#### Response

| Field         | Type    | Description                     |
| ------------- | ------- | ------------------------------- |
| `uuid`        | UUID    | Membership record UUID          |
| `member_id`   | UUID    | Member UUID                     |
| `amount`      | decimal | Payment amount                  |
| `amount_paid` | decimal | Total amount paid on membership |
| `date`        | string  | Derived from `start_date`       |
| `start_date`  | string  | Membership start                |
| `end_date`    | string  | Membership end                  |
| `mode`        | string  | Payment mode                    |
| `plan`        | string  | Plan name                       |
| `status`      | string  | Membership status               |

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

List all membership records, optionally filtered by member.

**Permission:** `IsAdminOrGymOwner`

**Query parameters:**

| Param       | Type | Required | Description           |
| ----------- | ---- | -------- | --------------------- |
| `member_id` | UUID | No       | Filter by member UUID |

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

### POST `/api/attendance/checkin/`

Record a member's gym check-in.

**Permission:** `IsGymOwnerOrTrainer`

#### Request

| Field       | Type     | Required | Description                     |
| ----------- | -------- | -------- | ------------------------------- |
| `member_id` | UUID     | Yes      | Member's UUID                   |
| `timestamp` | datetime | Yes      | Check-in time (ISO-8601)        |
| `lat`       | decimal  | No       | Latitude (up to 9,6 precision)  |
| `lng`       | decimal  | No       | Longitude (up to 9,6 precision) |

#### Response

| Field           | Type             | Description            |
| --------------- | ---------------- | ---------------------- |
| `uuid`          | UUID             | Attendance record UUID |
| `member`        | UUID             | Member UUID            |
| `check_in`      | datetime         | Check-in timestamp     |
| `check_out`     | datetime \| null | Check-out timestamp    |
| `check_in_lat`  | decimal \| null  | Check-in latitude      |
| `check_in_lng`  | decimal \| null  | Check-in longitude     |
| `check_out_lat` | decimal \| null  | Check-out latitude     |
| `check_out_lng` | decimal \| null  | Check-out longitude    |

#### Example JSON Request

```json
{
  "member_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "timestamp": "2026-06-30T06:00:00Z",
  "lat": "19.075984",
  "lng": "72.877656"
}
```

#### Example JSON Response

```json
{
  "uuid": "e5f6a7b8-c9d0-1234-ef01-345678901234",
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "check_in": "2026-06-30T06:00:00Z",
  "check_out": null,
  "check_in_lat": "19.075984",
  "check_in_lng": "72.877656",
  "check_out_lat": null,
  "check_out_lng": null
}
```

---

### POST `/api/attendance/checkout/`

Record a member's gym check-out against an existing check-in record.

**Permission:** `IsGymOwnerOrTrainer`

#### Request

| Field           | Type     | Required | Description                     |
| --------------- | -------- | -------- | ------------------------------- |
| `attendance_id` | UUID     | Yes      | UUID of the check-in record     |
| `timestamp`     | datetime | Yes      | Check-out time (ISO-8601)       |
| `lat`           | decimal  | No       | Latitude (up to 9,6 precision)  |
| `lng`           | decimal  | No       | Longitude (up to 9,6 precision) |

#### Example JSON Request

```json
{
  "attendance_id": "e5f6a7b8-c9d0-1234-ef01-345678901234",
  "timestamp": "2026-06-30T07:30:00Z",
  "lat": "19.075984",
  "lng": "72.877656"
}
```

#### Example JSON Response

```json
{
  "uuid": "e5f6a7b8-c9d0-1234-ef01-345678901234",
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "check_in": "2026-06-30T06:00:00Z",
  "check_out": "2026-06-30T07:30:00Z",
  "check_in_lat": "19.075984",
  "check_in_lng": "72.877656",
  "check_out_lat": "19.075984",
  "check_out_lng": "72.877656"
}
```

---

### GET `/api/attendance/`

List attendance records, optionally filtered by member and/or date.

**Permission:** `IsGymOwnerOrTrainer`

**Query parameters:**

| Param       | Type   | Required | Description                   |
| ----------- | ------ | -------- | ----------------------------- |
| `member_id` | UUID   | No       | Filter by member UUID         |
| `date`      | string | No       | Filter by date (`YYYY-MM-DD`) |

#### Example JSON Response

```json
[
  {
    "uuid": "e5f6a7b8-c9d0-1234-ef01-345678901234",
    "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "check_in": "2026-06-30T06:00:00Z",
    "check_out": "2026-06-30T07:30:00Z",
    "check_in_lat": "19.075984",
    "check_in_lng": "72.877656",
    "check_out_lat": "19.075984",
    "check_out_lng": "72.877656"
  }
]
```

---

## 10. Reports

All report endpoints are scoped to the requesting gym owner's gym.

### GET `/api/reports/inactive-members/`

Returns members whose last check-in is older than N days, or who have never checked in.

**Permission:** `IsGymOwner`

**Query parameters:**

| Param  | Type    | Required | Description                                 |
| ------ | ------- | -------- | ------------------------------------------- |
| `days` | integer | No       | Inactivity threshold in days (default: `7`) |

#### Response

| Field           | Type           | Description                                 |
| --------------- | -------------- | ------------------------------------------- |
| `member_id`     | UUID           | Member UUID                                 |
| `name`          | string         | Full name                                   |
| `last_visit`    | string \| null | Last check-in date; `null` if never visited |
| `days_inactive` | integer        | Days since last visit                       |

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
    "days_inactive": 999
  }
]
```

---

### GET `/api/reports/trainer-workload/`

Returns each trainer in the gym along with the count of their active members.

**Permission:** `IsGymOwner`

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

Returns members whose membership expires within the next X days (includes already-expired within the window).

**Permission:** `IsGymOwner`

**Query parameters:**

| Param  | Type    | Required | Description                             |
| ------ | ------- | -------- | --------------------------------------- |
| `days` | integer | No       | Lookahead window in days (default: `7`) |

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
| `member`        | UUID             | Member UUID                         |
| `check_in`      | datetime         | Check-in timestamp                  |
| `check_out`     | datetime \| null | Check-out timestamp                 |
| `check_in_lat`  | decimal \| null  | Check-in latitude                   |
| `check_in_lng`  | decimal \| null  | Check-in longitude                  |
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
| `errors`          | array   | List of error objects                       |
| `errors[].model`  | string  | Model identifier                            |
| `errors[].action` | string  | Action that failed                          |
| `errors[].error`  | string  | Error description                           |

#### Example JSON Request

```json
{
  "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "changes": [
    {
      "model": "attendance.Attendance",
      "action": "create",
      "data": {
        "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
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

**Query parameters:**

| Param     | Type     | Required | Description                                                 |
| --------- | -------- | -------- | ----------------------------------------------------------- |
| `user_id` | UUID     | No       | Filter records by member UUID                               |
| `since`   | datetime | No       | ISO-8601 timestamp; returns records updated after this time |

#### Response

| Field                | Type  | Description                                      |
| -------------------- | ----- | ------------------------------------------------ |
| `changes.attendance` | array | List of attendance records updated since `since` |

#### Example JSON Response

```json
{
  "changes": {
    "attendance": [
      {
        "uuid": "e5f6a7b8-c9d0-1234-ef01-345678901234",
        "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
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

## Schema & Documentation

| Endpoint       | Description               |
| -------------- | ------------------------- |
| `GET /schema/` | OpenAPI 3.0 schema (JSON) |
| `GET /docs/`   | Swagger UI                |
