# Fit&Fuel API Documentation

**Version:** Phase 1–3 (core CRUD, membership/payment tracking, attendance/reports/backup/music/notification templates)  
**Last full rewrite:** 2026-09-23. Rebuilt from the server code, not from git history. Where this doc and the code disagree, the code wins, so please flag the mismatch.  
**Base URL:** `http://<host>/` (no version prefix; trailing slash required on every route)  
**Authentication:** JWT Bearer Token — send `Authorization: Bearer <access_token>` on every protected endpoint.  
**Response format:** Every endpoint except `GET /api/my-ip/` and `HEAD /api/health/` wraps its response in `{data, message, status, time}`, plus `count`/`next`/`previous` on paginated lists — see [Standard response envelope](#standard-response-envelope). The examples below show this full wrapped shape unless a section says otherwise.

> **Verification note:** No Python/Django runtime was available while writing this doc, so behaviour was worked out by reading the source and `tests.py` files. A few statements depend on library defaults (DRF 3.16 / SimpleJWT 5.5.0 message texts, GeoIP2 field formats) rather than project code. Those spots say *"not verified at runtime"* or similar.

---

## Table of Contents

- [Conventions](#conventions)
- [Permission Roles](#permission-roles)
- [Enumerations](#enumerations)

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
14. [Notifications](#14-notifications)
15. [Known Issues & Implementation Notes](#15-known-issues--implementation-notes)

- [Schema & Documentation](#schema--documentation)

---

## Conventions

### Base URL & routing

**Base URL:** `http://<host>/` (no version prefix). Top-level mounts from `fit_&_fuel/urls.py`:

| Prefix | Included from | Contents |
| --- | --- | --- |
| `/admin/` | `django.contrib.admin` | Django admin site |
| `/auth/` | `accounts.urls` | Login, refresh, logout, profile, etc. |
| `/gyms/` | `accounts.urls_gyms` | Gym master data |
| `/users/` | `accounts.urls_users` | Gym-owner / trainer / member management |
| `/trainer/` | `accounts.urls_trainer` | Trainer panel |
| `/member/` | `accounts.urls_member` | Member panel |
| `/` | `accounts.urls_memberships` | `/memberships/`, `/payments/` |
| `/api/` | `core.urls` | Utility endpoints (`health/`, `my-ip/`, `upload-file/`) |
| `/api/attendance/` | `attendance.urls` | Attendance |
| `/api/reports/` | `reports.urls` | Reports |
| `/api/backup/` | `backup.urls` | Backup / sync |
| `/api/payments/` | `accounts.urls_member_payments` | Member payments (Phase 3) |
| `/api/music/` | `music.urls` | Music |
| `/api/notifications/` | `notifications.urls` | Notification templates |
| `/schema/`, `/docs/` | `drf_spectacular` | OpenAPI schema / Swagger UI |
| `/media/…` | Django `serve` / `static()` | Uploaded files (see [Media files](#media-files--uploads)) |

**Trailing slashes are required.** `APPEND_SLASH = True`, and every route is declared with a trailing `/`. A `GET` without the slash is 301-redirected; a `POST`/`PUT`/`DELETE` without the slash cannot be redirected with its body (Django raises a `RuntimeError` in `DEBUG`, and redirects to a `GET` otherwise). Always send the trailing slash.

`ALLOWED_HOSTS = ["*"]`. `DEBUG` is `True` only when the env var `DJANGO_ENV == "development"` (default `"production"`).

### Authentication

| Setting | Value |
| --- | --- |
| Default authentication class | `rest_framework_simplejwt.authentication.JWTAuthentication` (only one — no session/basic auth for API views) |
| Default permission class | `rest_framework.permissions.IsAuthenticated` (every DRF view requires a valid access token unless it overrides this) |
| Header | `Authorization: Bearer <access_token>` (`AUTH_HEADER_TYPES = ("Bearer",)`) |
| Algorithm | `HS256`, signed with env `JWT_SECRET_KEY` (`SIGNING_KEY`) |
| Access token lifetime | env `ACCESS_TOKEN_TIME` minutes, default `1440` (24 hours) |
| Refresh token lifetime | env `REFRESH_TOKEN_TIME` minutes, default `43200` (30 days) |
| Refresh rotation | `ROTATE_REFRESH_TOKENS = True` — `/auth/token/refresh/` returns a **new** `refresh` along with the new `access` |
| Blacklist after rotation | `BLACKLIST_AFTER_ROTATION = True` — the refresh token you just used is blacklisted; reusing it fails with `401` (`token_blacklist` app installed) |
| `UPDATE_LAST_LOGIN` | `True` — `last_login` is updated on login |
| User id claim | `user_id` in the token payload holds the user's `uuid` (`USER_ID_FIELD = "uuid"`, `USER_ID_CLAIM = "user_id"`) |
| Token classes accepted for auth | `AccessToken` only (a refresh token in the `Authorization` header is rejected) |
| Obtain serializer | `accounts.serializers.LoginSerializer` |

Views built on `core.views.NoAuthAPIView` / `NoAuthNoPermMixin` set `authentication_classes = []` and `permission_classes = []` — they are public, and a token sent to them is **ignored** (`request.user` is anonymous).

Authentication failures on views using the envelope renderer (see below) are rendered inside the envelope:

| Situation | Status | `message` |
| --- | --- | --- |
| No `Authorization` header | `401` | `"Authentication credentials were not provided."` |
| Invalid / expired / wrong-type access token | `401` | `"Given token not valid for any token type"` (SimpleJWT's `code`/`messages` keys are dropped by the renderer, see below) |
| Authenticated but role check fails | `403` | The permission class's `message` (see [Permission Roles](#permission-roles)) |

### Standard response envelope

Produced by `core/renderers.py::ResponseRenderer`. It is **not** set as a global default (`DEFAULT_RENDERER_CLASSES` is not configured); it is applied per view via the base classes in `core/views.py` (`BaseAPIView`, `NoAuthAPIView`, `BaseModelViewSet`, `BaseReadOnlyModelViewSet`) and explicitly on `LoginView` / `TokenRefreshAPIView`. Every DRF view in the project uses one of these, **except** `GET /api/my-ip/` (plain `JSONRenderer`, no envelope) and `HEAD /api/health/` (plain Django view, no body).

Every enveloped response has these top-level keys:

| Field | Type | Description |
| --- | --- | --- |
| `data` | any \| null | Payload (see rules below) |
| `message` | string \| object \| array | Human-readable message; on errors may be the raw error object (see below) |
| `status` | integer | HTTP status code (mirrors the real status) |
| `time` | string | Server time from `datetime.datetime.now()` — a **naive** ISO-8601 string with no timezone suffix, e.g. `"2026-09-23T10:15:30.123456"` (microseconds omitted when zero) |
| `count` | integer | Only on paginated list responses |
| `next` | string \| null | Only on paginated list responses — absolute URL of the next page |
| `previous` | string \| null | Only on paginated list responses — absolute URL of the previous page |

#### Success (2xx) rules

| View returned | Resulting envelope |
| --- | --- |
| Paginated dict (`results` + `count`) | `data` = the `results` list; `count`, `next`, `previous` added at top level; `message` = `""` |
| A string | `data` = the string **and** `message` = the string |
| A dict | `message` = the dict's `detail` key (popped out of `data`), else `""`; `data` = the rest of the dict |
| A list / anything else | `data` = the value as-is; `message` = `""` |

#### Example JSON Response — single object

```json
{
  "data": { "uuid": "8c1c…", "name": "Iron Temple" },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123456"
}
```

#### Example JSON Response — dict with `detail` (e.g. login)

View returned `{"detail": "Login successful", "access": "…", "refresh": "…"}`:

```json
{
  "data": { "access": "…", "refresh": "…" },
  "message": "Login successful",
  "status": 200,
  "time": "2026-09-23T10:15:30.123456"
}
```

#### Example JSON Response — plain string

View returned `"Logged out successfully."`:

```json
{
  "data": "Logged out successfully.",
  "message": "Logged out successfully.",
  "status": 200,
  "time": "2026-09-23T10:15:30.123456"
}
```

#### Example JSON Response — paginated list

```json
{
  "data": [ { "uuid": "…" }, { "uuid": "…" } ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123456",
  "count": 57,
  "next": "http://<host>/users/members/?page=3&page_size=20",
  "previous": "http://<host>/users/members/?page=1&page_size=20"
}
```

An unpaginated list (e.g. an `OptionalPagination` endpoint called without `page_size`) has `data` = the full array and **no** `count`/`next`/`previous` keys.

#### Error (non-2xx) rules

There is **no custom exception handler** (`EXCEPTION_HANDLER` is not set), so DRF's default handler builds the error body and the renderer then reshapes it:

| Error body | Resulting envelope |
| --- | --- |
| Dict containing `detail` (all DRF `APIException`s: `NotAuthenticated`, `PermissionDenied`, `NotFound`, `MethodNotAllowed`, `ConflictException`, SimpleJWT errors, …) | `data` = `null`; `message` = the `detail` string. Any other keys in the dict (e.g. SimpleJWT's `code`, `messages`) are **dropped** |
| A string (view returned `Response("…", status=4xx)`) | `data` = the string **and** `message` = the string |
| Dict without `detail` (serializer validation errors: `{"field": ["msg", …]}`) | `data` = the error dict **and** `message` = the same error dict (not a string) |
| A list (e.g. `ValidationError(["msg"])`) | `data` = the list **and** `message` = the same list |

#### Example JSON Response — `APIException` (e.g. 403)

```json
{
  "data": null,
  "message": "Admin access required.",
  "status": 403,
  "time": "2026-09-23T10:15:30.123456"
}
```

#### Example JSON Response — validation error (400)

```json
{
  "data": { "phone_number": ["This field is required."] },
  "message": { "phone_number": ["This field is required."] },
  "status": 400,
  "time": "2026-09-23T10:15:30.123456"
}
```

Clients should therefore treat `message` as `string | object | array` on error responses and, when it is not a string, derive a display message from the field-error dict.

#### `204 No Content`

Several delete endpoints return `Response(status=204)`. The renderer still produces an envelope (`{"data": null, "message": "", "status": 204, "time": "…"}`) as the body, but many HTTP stacks/clients discard bodies on `204` — clients should rely only on the status code.

### Custom exceptions (`core/exceptions.py`)

| Class | Status | `default_detail` | `default_code` | Used by |
| --- | --- | --- | --- | --- |
| `ConflictException` | `409` | `"Conflict."` | `conflict` | `accounts/user_views.py` — duplicate phone number on user creation, raised as `ConflictException("This phone number is already registered.")` → envelope `message: "This phone number is already registered."`, `data: null`, `status: 409` |

That is the only file in `core/exceptions.py`; there is no custom exception handler.

### Pagination (`core/pagination.py`)

Global default: `DEFAULT_PAGINATION_CLASS = "core.pagination.CustomPagination"`, `PAGE_SIZE = 20`. Applies to list actions of generic views/viewsets that don't override `pagination_class`.

**`CustomPagination`** (`PageNumberPagination`) — always paginates.

| Query param | Type | Required | Description |
| --- | --- | --- | --- |
| `page` | integer \| `"last"` | No | 1-based page number (default `1`; DRF also accepts `last`) |
| `page_size` | integer | No | Items per page, default `20`, capped at `100`. A non-positive or non-integer value silently falls back to `20` |

An out-of-range/invalid `page` → `404` with `message: "Invalid page."`.

**`OptionalPagination`** (`PageNumberPagination`) — paginates **only** when `page_size` is a positive integer. Used by `PaymentViewSet` (`accounts/user_views.py`) and list views in `attendance`, `reports`, `backup`, `music`.

| Query param | Type | Required | Description |
| --- | --- | --- | --- |
| `page_size` | integer | No | Omitted, `0`, negative, or non-integer → **no pagination** (full list in `data`, no `count`/`next`/`previous`). Positive → paginate with that size, capped at `100` |
| `page` | integer \| `"last"` | No | Page number; only meaningful when `page_size` is positive |

### Parsers & filtering

- `DEFAULT_PARSER_CLASSES`: `JSONParser`, `FormParser`, `MultiPartParser` — every endpoint accepts `application/json`, `application/x-www-form-urlencoded`, and `multipart/form-data`.
- `DEFAULT_FILTER_BACKENDS`: `django_filters.rest_framework.DjangoFilterBackend` — only has an effect on views that declare `filterset_fields`/`filterset_class`.
- No browsable API: views override `renderer_classes` with `ResponseRenderer` only.

### ViewSet conventions (`core/views.py`)

| Base class | Renderer | Allowed methods | Notes |
| --- | --- | --- | --- |
| `BaseAPIView` (`GenericAPIView`) | `ResponseRenderer` | as defined | Default auth/permission (authenticated) |
| `NoAuthAPIView` (`GenericAPIView`) | `ResponseRenderer` | as defined | `authentication_classes = []`, `permission_classes = []` — public |
| `BaseModelViewSet` (`ModelViewSet`) | `ResponseRenderer` | `GET`, `POST`, `PUT`, `DELETE`, `HEAD`, `OPTIONS` | **`PATCH` is disabled (405).** Partial updates go through the extra action `POST /<resource>/{pk}/update/` (`partial_update_via_post` → `partial_update`). `PUT /<resource>/{pk}/` is a full update |
| `BaseReadOnlyModelViewSet` (`ReadOnlyModelViewSet`) | `ResponseRenderer` | `GET`, `HEAD`, `OPTIONS` | List + retrieve only |
| `NoAuthNoPermMixin` | — | — | Mixin setting empty auth & permission classes |

### Common model fields (`core/models.py::BaseModel`)

Abstract base for most business models (e.g. `Gym`, `Membership`, `Payment`, `NotificationTemplate`). `CustomUser` does **not** extend it but declares the same audit/soft-delete fields itself (with `status` also set to `deleted` on soft delete).

| Field | Type | Description |
| --- | --- | --- |
| `uuid` | UUID (primary key) | `uuid4`, not editable. All `{uuid}` / `{pk}` path params are this value |
| `created_at` | datetime | Set on create (`auto_now_add`), indexed |
| `updated_at` | datetime | Set on every save (`auto_now`) |
| `created_by` | FK → user \| null | Not editable via forms; `SET_NULL` on user delete |
| `updated_by` | FK → user \| null | Not editable via forms; `SET_NULL` on user delete |
| `is_deleted` | boolean | Soft-delete flag, default `false`, indexed |
| `deleted_at` | datetime \| null | Set by `soft_delete()` |

Managers: `objects` (all rows, **including** soft-deleted) and `active_objects` (`is_deleted=False`). `soft_delete(deleted_by=None)` sets `is_deleted=True`, `deleted_at=now()`, optionally `updated_by`, and saves only those fields plus `updated_at`. Whether a given endpoint hard- or soft-deletes, and whether its queryset uses `active_objects`, is decided per view — see the endpoint sections.

`DailyRequestCount` (table `daily_request_counts`, not a `BaseModel`): `date` (unique date), `count` (positive int, default 0).

### Date / time / number formats

| Kind | Format |
| --- | --- |
| Model datetimes (`created_at`, `paid_on`, …) | ISO-8601 in UTC with `Z` (`USE_TZ = True`, `TIME_ZONE = "UTC"`), e.g. `"2026-09-23T10:15:30.123456Z"` |
| Dates | `YYYY-MM-DD` |
| Envelope `time` | Naive `datetime.now()` ISO string, no `Z` (see envelope) |
| Decimals (`amount`, `latitude`, …) | Serialized as **strings** (DRF default `COERCE_DECIMAL_TO_STRING`), e.g. `"1500.00"` |
| UUIDs | Canonical hyphenated string |

"Today" computations (`timezone.localdate()`) are in UTC since `TIME_ZONE = "UTC"`.

### Middleware effects

Order: `CorsMiddleware`, `SecurityMiddleware`, `SessionMiddleware`, `CommonMiddleware`, `CsrfViewMiddleware`, `AuthenticationMiddleware`, `MessageMiddleware`, `XFrameOptionsMiddleware`, `core.middleware.RequestCounterMiddleware`.

**`RequestCounterMiddleware`** — on every request whose path does **not** start with `/admin/`, `/media/`, `/static/`, `/schema/`, `/docs/`, increments today's (`timezone.localdate()`, UTC) `DailyRequestCount.count` with an atomic `F("count") + 1` update (creating the row with `count=1` if missing). It runs **before** the view, so it counts unauthenticated, failing, 404, `OPTIONS` preflight, and `HEAD /api/health/` requests too. Read back by `GET /api/reports/api-requests-today/` (admin only). No response headers or body are changed.

CSRF middleware is present but does not affect API calls (DRF views are CSRF-exempt and JWT auth doesn't enforce CSRF). It does apply to the Django admin.

### CORS

`django-cors-headers` with `CORS_ALLOW_ALL_ORIGINS = True` — any origin may call the API from a browser. No other CORS settings (default allowed headers include `authorization` and `content-type`; credentials not enabled).

### Throttling

None. No `DEFAULT_THROTTLE_CLASSES`/rates are configured and no view sets `throttle_classes`.

### Media files & uploads

| Setting | Value |
| --- | --- |
| `MEDIA_URL` | `/media/` |
| `MEDIA_ROOT` | `<BASE_DIR>/media` |
| Storage | Django default `FileSystemStorage` |
| Serving | Served **by Django itself** in both modes: `static()` helper when `DEBUG`; when not `DEBUG`, `re_path(r"^media/(?P<path>.*)$", serve)` (and the same for `/static/` from `STATIC_ROOT`) |
| Global upload size limit | None configured (Django defaults only: files over 2.5 MB are streamed to a temp file; no hard cap on request body for file parts). The 5 MB limit is enforced only by `POST /api/upload-file/` |

**Image fields use a two-step upload.** Model image fields (`profile_picture`, `gym_picture`, attendance `photo`, music `thumb`/`icon`/`cover`) are exposed through `core.serializers.UploadedFileURLField`:

- **Write:** expects the URL string returned by `POST /api/upload-file/`, not a raw file. The URL's path must start with `/media/`; the remainder is taken as the storage-relative path and must exist in storage. The host part of the URL is **not** checked. Defaults: `required=False`, `allow_null=True` (music fields override with `required=True`). Sending `null` clears the field (where `allow_null` holds).
- **Read:** rendered as the file's absolute URL (`http(s)://<host>/media/<path>`), or `null`.

| Error | When |
| --- | --- |
| `"Expected the URL returned by POST /api/upload-file/, not a raw file."` | Value is not a non-empty string (e.g. a multipart file, or `""`) |
| `"Must be a URL returned by POST /api/upload-file/."` | URL path doesn't start with `/media/` |
| `"Uploaded file not found."` | No such file under `MEDIA_ROOT` |

### Logging

Logs are written to `<BASE_DIR>/logs/` (`logs.log`, `errors.log`) and the console. Not client-visible.

---

## Permission Roles

All permission classes live in `core/permissions.py`; no other module defines a permission class. Every role class requires `request.user` to be authenticated **and** checks `request.user.user_type`. When the caller is unauthenticated, DRF returns `401 "Authentication credentials were not provided."` instead of the class's `403` message.

| Class | Condition | `403` message |
| --- | --- | --- |
| `IsAuthenticated` (DRF, global default) | Authenticated user | — (401 only) |
| `IsAuthenticatedUser` | Subclass of DRF `IsAuthenticated` (same condition) | `"You do not have access to this resource."` (only ever shown if DRF reports it; unauthenticated callers still get 401) |
| `IsAdmin` | `user_type == "admin"` | `"Admin access required."` |
| `IsGymOwner` | `user_type == "gym_owner"` | `"Gym Owner access required."` |
| `IsTrainer` | `user_type == "trainer"` | `"Trainer access required."` |
| `IsMember` | `user_type == "member"` | `"Member access required."` |
| `IsAdminOrGymOwner` | `user_type` in (`"admin"`, `"gym_owner"`) | `"Admin or Gym Owner access required."` |

None of these classes implement `has_object_permission`; object-level scoping (e.g. a gym owner only seeing their own gym's members) is done by each view's queryset. Views may combine classes with `|` (e.g. `IsGymOwner | IsTrainer`); when a combined check fails, DRF reports the message of the failing class(es).

`user_type` / `status` are not checked beyond this — account `status` enforcement (disabled/suspended) happens in the login serializer and auth layer (see §1). SimpleJWT's authentication additionally rejects users with `is_active = False` (`401`).

---

## Enumerations

Wire values are the lowercase snake_case strings in the **Value** column.

### `user_type` (`accounts.models.UserType`)

| Value | Label |
| --- | --- |
| `admin` | Admin |
| `gym_owner` | Gym Owner |
| `trainer` | Trainer |
| `member` | Member |

Default on `CustomUser`: `member`. `createsuperuser` defaults to `admin`.

### User `status` (`accounts.models.UserStatus`)

| Value | Label |
| --- | --- |
| `active` | Active |
| `disabled` | Disabled |
| `suspended` | Suspended |
| `deleted` | Deleted |

Default: `active`. `CustomUser.soft_delete()` sets `status = "deleted"` together with `is_deleted = true`.

### `gender` (`accounts.models.GenderChoice`)

| Value | Label |
| --- | --- |
| `male` | Male |
| `female` | Female |
| `other` | Other |

Blank (`""`) is allowed on `CustomUser.gender`.

### Membership `status` (`accounts.models.MembershipStatus`) and `CustomUser.membership_status`

| Value | Label |
| --- | --- |
| `active` | Active |
| `expired` | Expired |

`Membership.status` defaults to `active`. `CustomUser.membership_status` uses the same two values via an inline choices list and is nullable.

### Payment `mode` (`accounts.models.PaymentMode`) — used by `Membership.payment_mode` and `Payment.mode`

| Value | Label |
| --- | --- |
| `cash` | Cash |
| `online` | Online |

Note: the Phase-3 input serializer `MemberPaymentSerializer.mode` (`POST /api/payments/`) instead declares `ChoiceField(choices=["Cash", "Online"])` — **capitalised** values, which differ from the model's `cash`/`online`. See §8 for how it is mapped.

### Payment `status` (`accounts.models.PaymentStatus`)

| Value | Label |
| --- | --- |
| `paid` | Paid |
| `pending` | Pending |
| `overdue` | Overdue |

Default: `paid`.

### Other apps

`notifications.models.NotificationCategory`: `general`, `promotion`, `alert`, `reminder` (see §14).

### Other `CustomUser` defaults relevant to clients

- `trainer_limit`: integer, default `5`.
- `phone_number`: unique, max 15 chars; it is the login identifier (`USERNAME_FIELD`).
- `Payment.invoice_number`: auto-generated on first save as `INV-<YYYYMMDD>-<first 6 hex chars of uuid, uppercased>`.

---

## 1. Authentication

All routes in this section come from `accounts/urls.py`, mounted at `/auth/` in `fit_&_fuel/urls.py`. There are six endpoints:

| Method | Path                     | View                  | Auth          |
| ------ | ------------------------ | --------------------- | ------------- |
| POST   | `/auth/login/`           | `LoginView`           | Public        |
| POST   | `/auth/token/refresh/`   | `TokenRefreshAPIView` | Public        |
| POST   | `/auth/logout/`          | `LogoutView`          | Authenticated |
| GET    | `/auth/profile/`         | `MeView`              | Authenticated |
| POST   | `/auth/profile/update/`  | `ProfileUpdateView`   | Authenticated |
| POST   | `/auth/change-password/` | `ChangePasswordView`  | Authenticated |

> The comment in `fit_&_fuel/urls.py` mentions `/auth/me/`. That route does not exist. The current-user endpoint is `/auth/profile/`.

### Response envelope (applies to every endpoint below)

All six views render through `core.renderers.ResponseRenderer`. That includes the two SimpleJWT-based views (`LoginView`, `TokenRefreshAPIView`), which set `renderer_classes` explicitly. DRF renders error responses, including those raised by exceptions, with the view's renderer, so errors are wrapped in the envelope too. What the view returns is transformed like this:

| View returns                                   | Status | `data`                         | `message`                       |
| ---------------------------------------------- | ------ | ------------------------------ | ------------------------------- |
| a plain string                                 | any    | the string                     | the same string                 |
| a dict containing `detail`                     | 2xx    | the dict without `detail`      | the value of `detail`           |
| a dict without `detail`                        | 2xx    | the dict                       | `""`                            |
| a dict containing `detail` (e.g. auth/JWT errors) | non-2xx | `null`                     | the value of `detail`           |
| a dict without `detail` (serializer validation errors) | non-2xx | the error dict       | **the same error dict** (not a string) |

The envelope also has `status` (the HTTP status code) and `time`. `time` is `datetime.datetime.now()` on the server: naive local time with no timezone offset, ISO-8601 formatted.

```json
{
  "data": { "...": "..." },
  "message": "",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

### Common errors on authenticated endpoints

Authenticated endpoints (`logout`, `profile`, `profile/update`, `change-password`) use the global defaults: `JWTAuthentication` and `IsAuthenticated`. Send `Authorization: Bearer <access_token>`.

| Status | When                                                   | Body                                                                                                  |
| ------ | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `401`  | No `Authorization` header                              | `{"data": null, "message": "Authentication credentials were not provided.", "status": 401, "time": "..."}` |
| `401`  | Access token is malformed, expired, or a refresh token was sent | `data: null`, `message: "Given token not valid for any token type"` (SimpleJWT `InvalidToken`) |
| `401`  | Token's user no longer exists / has `is_active = false` | `message: "User not found"` / `"User is inactive"` (SimpleJWT defaults)                             |
| `405`  | Wrong HTTP method (e.g. `PUT`/`PATCH` on `/auth/profile/update/`) | `data: null`, `message: "Method \"PUT\" not allowed."`                                     |

> **Important:** JWT authentication checks only the Django `is_active` flag. It does **not** check `status` or `is_deleted`. A user whose `status` becomes `disabled`, `suspended`, or `deleted` after logging in can keep using their existing access token until it expires, and can keep refreshing it (see the note under `/auth/token/refresh/`). `status` is enforced only at login.

---

### POST `/auth/login/`

Log in with phone number and password. Returns a JWT access/refresh pair and a user snapshot.

**Permission:** Public (SimpleJWT `TokenObtainPairView`, which sets no authentication or permission classes)

Serializer: `accounts.serializers.LoginSerializer`, a subclass of `TokenObtainPairSerializer`. It is also set as `SIMPLE_JWT["TOKEN_OBTAIN_SERIALIZER"]`.

#### Request

JSON, form-encoded, or multipart are all accepted (the global parsers).

| Field          | Type   | Required | Description                                                                 |
| -------------- | ------ | -------- | --------------------------------------------------------------------------- |
| `phone_number` | string | Yes      | Registered phone number (the `USERNAME_FIELD`). Must not be blank. No format validation is applied. |
| `password`     | string | Yes      | Account password. Must not be blank.                                        |

#### Processing order

1. Field validation (both fields required and non-blank).
2. **Pre-check (before the password is verified):** the user is looked up by `phone_number`. If they exist, their account state is checked in this order:
   - `is_deleted = true` or `status = deleted` → 403 `"Account has been deleted."`
   - `status = disabled` → 403 `"Account is disabled."`
   - `status = suspended` → 403 `"Account is suspended."`
   - any other non-`active` status → 403 `"Account is not active."` (not reachable with the current `UserStatus` choices, but present in code)
   - Because this runs before password verification, a non-active account gets its 403 **even when the password is wrong**. This also reveals whether a phone number is registered.
3. Standard SimpleJWT authentication (Django `ModelBackend`, which also rejects `is_active = false`). Any failure here becomes a generic 401.

#### Side effects

- `SIMPLE_JWT["UPDATE_LAST_LOGIN"] = True`, so `last_login` on the user is updated on every successful login.
- The refresh token is recorded as an `OutstandingToken`, so it can be blacklisted later (the `token_blacklist` app is installed).

#### Token contents and lifetimes

- Standard claims: `token_type`, `exp`, `iat`, `jti`, and `user_id`, which holds the user's `uuid` (`USER_ID_FIELD = "uuid"`).
- Custom claims added by `LoginSerializer.get_token`: `user_type` and `status`. The access token inherits both. These values are captured **at login time**. They are carried over unchanged on refresh and do not reflect later role or status changes.
- Algorithm: `HS256`, signed with the `JWT_SECRET_KEY` env var.
- Access token lifetime: `ACCESS_TOKEN_TIME` minutes (env var, default **1440** = 24 h).
- Refresh token lifetime: `REFRESH_TOKEN_TIME` minutes (env var, default **43200** = 30 days).

#### Response

The view returns `{"detail": "Login successful", "refresh", "access", "user"}`. The renderer moves `detail` into `message`, so the tokens and user object arrive **inside `data`**.

| Field                    | Type         | Description                                                       |
| ------------------------ | ------------ | ----------------------------------------------------------------- |
| `message`                | string       | `"Login successful"`                                              |
| `data.refresh`           | string       | JWT refresh token                                                 |
| `data.access`            | string       | JWT access token                                                  |
| `data.user.uuid`         | string (UUID) | User identifier                                                  |
| `data.user.first_name`   | string       | First name (may be `""`)                                          |
| `data.user.last_name`    | string       | Last name (may be `""`)                                           |
| `data.user.phone_number` | string       | Phone number                                                      |
| `data.user.user_type`    | string       | `admin` \| `gym_owner` \| `trainer` \| `member`                   |
| `data.user.status`       | string       | Always `active` on success (other statuses are rejected)          |
| `data.user.gym_id`       | string (UUID) \| null | UUID of the gym-owner **user** this account belongs to (trainers/members). `null` for admins and gym owners. |
| `data.user.trainer_id`   | string (UUID) \| null | UUID of the assigned trainer user (members only), else `null` |

> The login snapshot does **not** include `gym_uuid` (the gym owner's `Gym` master record). Use `GET /auth/profile/` for that.

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
  "data": {
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
  },
  "message": "Login successful",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

#### Error Responses

| Status | When                                                                       | Body                                                                                           |
| ------ | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `400`  | `phone_number` or `password` missing/blank                                 | `data` and `message` both = e.g. `{"phone_number": ["This field is required."]}` / `{"password": ["This field may not be blank."]}` |
| `401`  | Phone not registered, wrong password, or `is_active = false`               | `data` = `message` = `"Invalid phone number or password."`                                     |
| `403`  | `is_deleted = true` or `status = deleted` (checked before password)        | `data` = `message` = `"Account has been deleted."`                                             |
| `403`  | `status = disabled` (checked before password)                              | `data` = `message` = `"Account is disabled."`                                                  |
| `403`  | `status = suspended` (checked before password)                             | `data` = `message` = `"Account is suspended."`                                                 |
| `403`  | Any other non-`active` status (defensive; not reachable with current enum) | `data` = `message` = `"Account is not active."`                                                |

Example 401:

```json
{
  "data": "Invalid phone number or password.",
  "message": "Invalid phone number or password.",
  "status": 401,
  "time": "2026-06-30T10:00:00.123456"
}
```

---

### POST `/auth/token/refresh/`

Exchange a valid refresh token for a new access token **and a new, rotated refresh token**.

**Permission:** Public (stock SimpleJWT `TokenRefreshView`; only `renderer_classes` is overridden, and `post()` is not overridden)

#### Request

| Field     | Type   | Required | Description       |
| --------- | ------ | -------- | ----------------- |
| `refresh` | string | Yes      | JWT refresh token |

#### Side effects

- `ROTATE_REFRESH_TOKENS = True` and `BLACKLIST_AFTER_ROTATION = True`. The submitted refresh token is **blacklisted**, and a new refresh token with a fresh `jti`, `iat`, and `exp` is returned. **Clients must store the new `refresh` from every response.** Reusing the old one returns 401.
- The new tokens copy the custom `user_type` and `status` claims from the old refresh token. Those claims are not re-read from the database.
- The test `AuthTests.test_token_refresh` confirms that both `access` and `refresh` are returned under `data`. The blacklisting and claim-copy behaviour is taken from `djangorestframework_simplejwt==5.5.0` (pinned in `requirements.txt`). It was not re-verified against the installed package source.
- SimpleJWT 5.5.0's `TokenRefreshSerializer` is expected to reject a token whose user fails `USER_AUTHENTICATION_RULE` (i.e. `is_active = false`). It does **not** check `status`, so disabled or suspended users can keep refreshing. The active-user check was not re-verified against the installed source.

#### Response

| Field          | Type   | Description                                    |
| -------------- | ------ | ---------------------------------------------- |
| `data.access`  | string | New JWT access token                           |
| `data.refresh` | string | New (rotated) JWT refresh token                |
| `message`      | string | `""`                                           |

#### Example JSON Request

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Example JSON Response

```json
{
  "data": {
    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "message": "",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

#### Error Responses

| Status | When                                                           | Body                                                                                                                                                  |
| ------ | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `400`  | `refresh` missing/blank                                        | `data` = `message` = `{"refresh": ["This field is required."]}` (or `"This field may not be blank."`)                                                  |
| `401`  | Token malformed, expired, wrong type, or already blacklisted   | SimpleJWT `InvalidToken` (`{"detail": "...", "code": "token_not_valid"}`), wrapped by the renderer: `data: null`, `message:` SimpleJWT's text, e.g. `"Token is blacklisted"` or an invalid/expired message. Exact wording comes from simplejwt 5.5.0. |
| `401`  | User in token has `is_active = false` (see note above)         | `data: null`, `message:` SimpleJWT's `no_active_account` text (unverified wording)                                                                    |

```json
{
  "data": null,
  "message": "Token is blacklisted",
  "status": 401,
  "time": "2026-06-30T10:00:00.123456"
}
```

---

### POST `/auth/logout/`

Blacklist the given refresh token so it can no longer be used to refresh.

**Permission:** Authenticated (any role)

#### Request

| Field     | Type   | Required | Description                     |
| --------- | ------ | -------- | ------------------------------- |
| `refresh` | string | Yes      | JWT refresh token to blacklist  |

#### Side effects and caveats

- Calls `RefreshToken(refresh).blacklist()`, which creates a `BlacklistedToken` row.
- The **access token is not revoked**. It stays valid until its own `exp`. Clients should discard it locally.
- The view does **not** check that the refresh token belongs to `request.user`. Any authenticated user holding another user's valid refresh token can blacklist it.

#### Response

| Field     | Type   | Description                  |
| --------- | ------ | ---------------------------- |
| `data`    | string | `"Logged out successfully."` |
| `message` | string | `"Logged out successfully."` |

#### Example JSON Request

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Example JSON Response

```json
{
  "data": "Logged out successfully.",
  "message": "Logged out successfully.",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

#### Error Responses

| Status | When                                                                                     | Body                                                                   |
| ------ | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `400`  | `refresh` missing/blank                                                                  | `data` = `message` = `{"refresh": ["This field is required."]}`         |
| `400`  | Token malformed, expired, wrong type (e.g. an access token was sent), or already blacklisted | `data` = `message` = `"Invalid or already blacklisted token."`      |
| `401`  | Missing/invalid access token                                                             | See [Common errors](#common-errors-on-authenticated-endpoints)         |

---

### GET `/auth/profile/`

Return the profile of the currently authenticated user.

**Permission:** Authenticated (any role)

Serializer: `UserMeSerializer`. Every field is read-only.

#### Response

| Field                   | Type                  | Description                                                                                                                  |
| ----------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `data.uuid`             | string (UUID)         | User identifier                                                                                                              |
| `data.phone_number`     | string                | Phone number (max 15 chars)                                                                                                  |
| `data.first_name`       | string                | First name (may be `""`)                                                                                                     |
| `data.last_name`        | string                | Last name (may be `""`)                                                                                                      |
| `data.date_of_birth`    | string (`YYYY-MM-DD`) \| null | Date of birth                                                                                                         |
| `data.age`              | integer \| null       | Computed from `date_of_birth` (`null` if no DOB)                                                                             |
| `data.gender`           | string                | `male` \| `female` \| `other` \| `""`                                                                                        |
| `data.profile_picture`  | string (absolute URL) \| null | Absolute URL built with the request host, e.g. `http://<host>/media/uploads/<hex>.jpg`                               |
| `data.experience_level` | string \| null        | Free text, max 50 chars                                                                                                      |
| `data.user_type`        | string                | `admin` \| `gym_owner` \| `trainer` \| `member`                                                                              |
| `data.status`           | string                | `active` \| `disabled` \| `suspended` \| `deleted`                                                                           |
| `data.gym_id`           | string (UUID) \| null | UUID of the gym-owner **user** this account belongs to (trainers/members). `null` for gym owners and admins.                |
| `data.gym_uuid`         | string (UUID) \| null | UUID of the `Gym` master record (`gym_details`). Set only for `gym_owner` accounts that have one, otherwise `null`.        |
| `data.trainer_id`       | string (UUID) \| null | UUID of the assigned trainer user (members), else `null`                                                                     |
| `data.created_at`       | string (ISO datetime, UTC) | Account creation timestamp                                                                                              |
| `message`               | string                | `""`                                                                                                                         |

#### Example JSON Response

```json
{
  "data": {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "phone_number": "9876543210",
    "first_name": "Raj",
    "last_name": "Sharma",
    "date_of_birth": "1990-05-15",
    "age": 35,
    "gender": "male",
    "profile_picture": "http://localhost:8000/media/uploads/9f1c2e7b4a5d4c0e8b3a1f2d6e7c8b9a.jpg",
    "experience_level": null,
    "user_type": "gym_owner",
    "status": "active",
    "gym_id": null,
    "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "trainer_id": null,
    "created_at": "2025-01-10T08:30:00.123456Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

#### Error Responses

| Status | When                          | Body                                                           |
| ------ | ----------------------------- | -------------------------------------------------------------- |
| `401`  | Missing/invalid access token  | See [Common errors](#common-errors-on-authenticated-endpoints) |

---

### POST `/auth/profile/update/`

Partially update the authenticated user's own profile. The view calls `partial=True`, so every field is optional. Only `POST` is allowed (`PUT`/`PATCH` return 405).

**Permission:** Authenticated (any role, including admin)

Serializer: `ProfileUpdateSerializer`. Read-only fields are **silently ignored** if sent: `uuid`, `phone_number`, `user_type`, `status`, `gym_id`, `gym_uuid`, `trainer_id`, `created_at`, `age`.

#### Request

JSON, form-encoded, and multipart bodies are all parsed. **`profile_picture` does not accept a file upload.** First upload the image to `POST /api/upload-file/` (multipart field `file`: jpg/jpeg/png/webp, max 5 MB). Then send the returned `url` string here. A raw file sent in `profile_picture` is rejected.

| Field              | Type                 | Required | Description / validation                                                                                                   |
| ------------------ | -------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------- |
| `first_name`       | string               | No       | Max 150 chars; blank allowed                                                                                               |
| `last_name`        | string               | No       | Max 150 chars; blank allowed                                                                                               |
| `date_of_birth`    | string \| null       | No       | `YYYY-MM-DD`; `null` clears                                                                                                |
| `gender`           | string               | No       | `male` \| `female` \| `other` (blank `""` also accepted, since the model field is `blank=True`)                           |
| `profile_picture`  | string (URL) \| null | No       | URL returned by `POST /api/upload-file/` (or any URL whose path starts with `/media/` and points to an existing stored file). Only the path part is used, so the host is ignored. `null` clears the picture. |
| `experience_level` | string \| null       | No       | Free text, max 50 chars; `null` allowed                                                                                    |

#### Side effects

- Sets `updated_by = request.user`, and `updated_at` is bumped automatically.
- Model `full_clean()` is **not** run on this endpoint. Only serializer-level field validation applies.

#### Response

Same fields as `GET /auth/profile/` (see that table), with the updated values, under `data`. `message` is `""`.

#### Example JSON Request

```json
{
  "experience_level": "5 years",
  "profile_picture": "http://localhost:8000/media/uploads/9f1c2e7b4a5d4c0e8b3a1f2d6e7c8b9a.jpg"
}
```

#### Example JSON Response

```json
{
  "data": {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "phone_number": "9876543210",
    "first_name": "Raj",
    "last_name": "Sharma",
    "date_of_birth": "1990-05-15",
    "age": 35,
    "gender": "male",
    "profile_picture": "http://localhost:8000/media/uploads/9f1c2e7b4a5d4c0e8b3a1f2d6e7c8b9a.jpg",
    "experience_level": "5 years",
    "user_type": "gym_owner",
    "status": "active",
    "gym_id": null,
    "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "trainer_id": null,
    "created_at": "2025-01-10T08:30:00.123456Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

#### Error Responses

All 400 bodies are the serializer error dict, placed in both `data` and `message`.

| Status | When                                                                    | Body (field errors)                                                                          |
| ------ | ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `400`  | `profile_picture` is a file, a non-string, or an empty string           | `{"profile_picture": ["Expected the URL returned by POST /api/upload-file/, not a raw file."]}` |
| `400`  | `profile_picture` URL path does not start with `/media/`                | `{"profile_picture": ["Must be a URL returned by POST /api/upload-file/."]}`                  |
| `400`  | `profile_picture` points to a file that does not exist in storage       | `{"profile_picture": ["Uploaded file not found."]}`                                           |
| `400`  | `gender` not one of the choices                                         | `{"gender": ["\"xyz\" is not a valid choice."]}` (DRF default)                                |
| `400`  | `date_of_birth` bad format                                              | `{"date_of_birth": ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]}` (DRF default) |
| `400`  | `first_name`/`last_name` > 150 chars, `experience_level` > 50 chars      | `{"<field>": ["Ensure this field has no more than N characters."]}` (DRF default)             |
| `401`  | Missing/invalid access token                                            | See [Common errors](#common-errors-on-authenticated-endpoints)                               |

---

### POST `/auth/change-password/`

Change the authenticated user's password.

**Permission:** Authenticated (any role)

#### Request

| Field          | Type   | Required | Description / validation                                                                                                                              |
| -------------- | ------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `old_password` | string | Yes      | Must match the current password                                                                                                                       |
| `new_password` | string | Yes      | At least 8 chars, and at least one each of: uppercase `A-Z`, lowercase `a-z`, digit, and special character from ``!@#$%^&*(),.?":{}\|<>-_=+[]\;'`~/``. Must differ from `old_password`. |

#### Side effects

- Calls `user.set_password(new_password)` and saves `password` and `updated_at`.
- **Existing JWTs are not invalidated.** Access and refresh tokens issued before the change keep working until they expire or are blacklisted. Nothing is blacklisted automatically.

#### Response

| Field     | Type   | Description                         |
| --------- | ------ | ----------------------------------- |
| `data`    | string | `"Password updated successfully."`  |
| `message` | string | `"Password updated successfully."`  |

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
  "data": "Password updated successfully.",
  "message": "Password updated successfully.",
  "status": 200,
  "time": "2026-06-30T10:00:00.123456"
}
```

#### Error Responses

All 400 bodies are the serializer error dict, placed in both `data` and `message`. Field-level errors for both fields are reported together. The "must differ" check runs only after both fields pass their own validation.

| Status | When                                   | Body (field errors)                                                                                          |
| ------ | -------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `400`  | Field missing/blank                    | `{"old_password": ["This field is required."]}` / `["This field may not be blank."]`                         |
| `400`  | `old_password` wrong                   | `{"old_password": ["Old password is incorrect."]}`                                                           |
| `400`  | `new_password` fails strength rules    | `{"new_password": [...]}`, which lists **every** failing rule from: `"Password must be at least 8 characters long."`, `"Password must contain at least one uppercase letter."`, `"Password must contain at least one lowercase letter."`, `"Password must contain at least one digit."`, `"Password must contain at least one special character."` |
| `400`  | `new_password == old_password`         | `{"new_password": ["New password must differ from old password."]}`                                         |
| `401`  | Missing/invalid access token           | See [Common errors](#common-errors-on-authenticated-endpoints)                                               |

Example 400:

```json
{
  "data": { "old_password": ["Old password is incorrect."] },
  "message": { "old_password": ["Old password is incorrect."] },
  "status": 400,
  "time": "2026-06-30T10:00:00.123456"
}
```

---

## 2. Gym Master

Master record for a gym's name, picture and location (`accounts.models.Gym`, table `gyms`). A gym owner's account points at its gym through `CustomUser.gym_details`, which is exposed as `gym_uuid` on gym-owner responses (see [User Management](#3-user-management)) and on `GET /auth/me/`.

**Router:** `accounts/urls_gyms.py` registers `GymViewSet` (a `core.views.BaseModelViewSet`) on a DRF `DefaultRouter` with an empty prefix, mounted at `/gyms/`. Lookup is the gym's `uuid`.

| Route                        | Method   | ViewSet action            | Exposed?                                                          |
| ---------------------------- | -------- | ------------------------- | ----------------------------------------------------------------- |
| `/gyms/`                     | `GET`    | `list`                    | Yes                                                               |
| `/gyms/`                     | `POST`   | `create`                  | Yes                                                               |
| `/gyms/{uuid}/`              | `GET`    | `retrieve`                | Yes                                                               |
| `/gyms/{uuid}/`              | `PUT`    | `update`                  | Yes                                                               |
| `/gyms/{uuid}/`              | `PATCH`  | `partial_update`          | **No** — `405`, `PATCH` isn't in `http_method_names` (see below)  |
| `/gyms/{uuid}/`              | `DELETE` | `destroy` (soft delete)   | Yes                                                               |
| `/gyms/{uuid}/update/`       | `POST`   | `partial_update_via_post` | Yes — this is the partial update                                  |
| `/gyms/{uuid}/enable/`       | `POST`   | `enable`                  | Yes                                                               |

`BaseModelViewSet` sets `http_method_names = ["get", "post", "put", "delete", "head", "options"]`, so every `PATCH` returns `405` with message `Method "PATCH" not allowed.`. Partial updates go through `POST .../update/` instead, which calls DRF's `partial_update()` internally.

**Permission (per action, from `GymViewSet.get_permissions`):**

| Action                                      | Permission class      | Queryset                                                                                                   |
| ------------------------------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------- |
| `list`, `retrieve`                          | `IsAuthenticatedUser` | Every non-deleted gym (`Gym.active_objects`). Any role (`admin`, `gym_owner`, `trainer`, `member`) sees all gyms, unscoped. |
| `update` (`PUT`), `update/` (`POST`)        | `IsAdminOrGymOwner`   | Admin: every non-deleted gym. Gym owner: only the gym whose `uuid` equals their own `gym_details_id`. Any other `uuid` returns `404`. A gym owner with no `gym_details` gets `404` for every gym. |
| `create`, `destroy`, `enable` (and `PATCH`) | `IsAdmin`             | `destroy`: non-deleted gyms. `enable`: **all** gyms, including soft-deleted ones (`Gym.objects`).           |

**Response envelope:** every response is wrapped by `core.renderers.ResponseRenderer`:

```json
{
  "data": { },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

- `time` is the server's local `datetime.now()` (naive, no timezone suffix).
- On a paginated list, `data` is the page's array, and `count`, `next` and `previous` are added at the top level.
- On an error with a `detail` key (permission, 404, 409, etc.), `data` is `null` and `message` holds the `detail` string.
- On a validation error (a dict of field errors, no `detail`), **both** `data` and `message` hold the same field-error dict.

**Common query parameters (list only):**

| Param       | Description                                                                                          |
| ----------- | ---------------------------------------------------------------------------------------------------- |
| `page`      | Page number (`CustomPagination`, 1-based). Out of range returns `404` with message `"Invalid page."` |
| `page_size` | Results per page. Default `20`, max `100`.                                                           |
| `search`    | `SearchFilter`, case-insensitive partial match on `name`                                            |
| `ordering`  | `OrderingFilter`. Allowed: `name`, `created_at` (prefix with `-` for descending). Default: `name`. Unknown fields are ignored. |

There are no field filters on `/gyms/`. `GymViewSet.filter_backends` overrides the global `DjangoFilterBackend` default and only includes `SearchFilter` and `OrderingFilter`.

**Gym object (`GymSerializer`):**

| Field         | Type           | Read-only | Description                                                                                                                                  |
| ------------- | -------------- | --------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `uuid`        | UUID           | Yes       | Gym identifier                                                                                                                               |
| `name`        | string         | No        | Gym name, max 255 chars                                                                                                                      |
| `gym_picture` | string \| null | No        | On read: the stored file's URL (see note below). On write: a URL returned by `POST /api/upload-file/`, or `null` to clear.                   |
| `latitude`    | string         | No        | Decimal, rendered as a string, e.g. `"18.520430"` (max 9 digits, 6 decimal places)                                                         |
| `longitude`   | string         | No        | Decimal, rendered as a string, e.g. `"73.856743"` (max 9 digits, 6 decimal places)                                                         |

`created_at`, `created_by`, `updated_by`, `is_deleted` and `deleted_at` exist on the model but are **not** returned.

**Image URL note:** `gym_picture` (and `profile_picture` in Section 3) is an `UploadedFileURLField`. When the serializer has the request in its context (list/retrieve/create/PUT/`update/`), the URL is absolute, e.g. `http://<host>/media/uploads/<hex>.jpg`. The custom `enable`, `disable` and `assign-trainer` actions build their serializer **without** a request context, so they return a relative path such as `/media/uploads/<hex>.jpg`. Files uploaded through `POST /api/upload-file/` live under `media/uploads/`. The model's `upload_to="gym_pictures/"` only applies to files assigned outside the API (for example, in Django admin).

**Location rule:** `latitude` and `longitude` are nullable at the DB level, so legacy rows keep working. `GymSerializer` redeclares them as `DecimalField(max_digits=9, decimal_places=6, allow_null=False)`, which makes them required on `POST /gyms/` and on a full `PUT`, and rejects an explicit `null` everywhere. A partial `POST .../update/` may omit them (the location stays unchanged) or change them, but can't clear them. **Range is not validated**: a latitude outside −90..90 or a longitude outside −180..180 is accepted as long as it fits 9 digits and 6 decimal places. These coordinates back the geofence check on [Attendance](#9-attendance) check-in/out.

---

### GET `/gyms/`

List all non-deleted gyms.

**Permission:** `IsAuthenticatedUser` (any authenticated role). Unscoped: every role sees every non-deleted gym.

**Query params:** `page`, `page_size`, `search` (`name`), `ordering` (`name`, `created_at`; default `name`).

#### Response

Paginated list of [Gym objects](#2-gym-master).

| Field                | Type           | Description                          |
| -------------------- | -------------- | ------------------------------------ |
| `data[]`             | array          | Gyms on this page                    |
| `data[].uuid`        | UUID           | Gym identifier                       |
| `data[].name`        | string         | Gym name                             |
| `data[].gym_picture` | string \| null | Absolute image URL                   |
| `data[].latitude`    | string \| null | Decimal string (`null` only on legacy rows) |
| `data[].longitude`   | string \| null | Decimal string (`null` only on legacy rows) |
| `count`              | integer        | Total matching gyms                  |
| `next`               | string \| null | Absolute URL of the next page        |
| `previous`           | string \| null | Absolute URL of the previous page    |

#### Example JSON Response

```json
{
  "data": [
    {
      "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
      "name": "Iron Paradise",
      "gym_picture": "http://localhost:8000/media/uploads/3f9c2a7b1d4e4f6a8b0c1d2e3f4a5b6c.jpg",
      "latitude": "18.520430",
      "longitude": "73.856743"
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123",
  "count": 1,
  "next": null,
  "previous": null
}
```

#### Error Responses

| Status | When                                   | Body                                                                   |
| ------ | -------------------------------------- | ---------------------------------------------------------------------- |
| `401`  | No `Authorization` header              | message: `"Authentication credentials were not provided."`             |
| `401`  | Invalid or expired token               | message: `"Given token not valid for any token type"` (simplejwt)      |
| `404`  | `page` out of range                    | message: `"Invalid page."`                                             |

---

### POST `/gyms/`

Create a gym master record. `created_by` is set to the requesting admin.

**Permission:** `IsAdmin`

This does **not** link the gym to any gym owner. `gym_details` isn't writable through any gym-owner endpoint. A gym owner's gym is created automatically by `POST /users/gym-owners/`, so a gym created here has no owner unless it's linked outside the API (for example, in Django admin).

#### Request

| Field         | Type              | Required | Description                                                                                         |
| ------------- | ----------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `name`        | string            | Yes      | Max 255 chars, not blank                                                                            |
| `gym_picture` | string \| null    | No       | Must be a URL whose path starts with `/media/` **and** points to an existing stored file (from `POST /api/upload-file/`). A raw multipart file is rejected. |
| `latitude`    | decimal \| string | Yes      | Max 9 digits total, 6 decimal places, not `null`                                                    |
| `longitude`   | decimal \| string | Yes      | Max 9 digits total, 6 decimal places, not `null`                                                    |

#### Response

`201 Created`. `data` is a Gym object (`uuid`, `name`, `gym_picture`, `latitude`, `longitude`).

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
  "data": {
    "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "name": "Iron Paradise",
    "gym_picture": null,
    "latitude": "18.520430",
    "longitude": "73.856743"
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                  | Body (`data` and `message` both carry the field-error dict for `400`)                          |
| ------ | ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `400`  | Missing field                         | `{"name": ["This field is required."], "latitude": ["This field is required."], ...}`          |
| `400`  | `latitude`/`longitude` sent as `null` | `{"latitude": ["This field may not be null."]}`                                                 |
| `400`  | Too many decimals / digits            | `["Ensure that there are no more than 6 decimal places."]` / `["Ensure that there are no more than 9 digits in total."]` |
| `400`  | `gym_picture` not a string            | `{"gym_picture": ["Expected the URL returned by POST /api/upload-file/, not a raw file."]}`      |
| `400`  | `gym_picture` path not under `/media/` | `{"gym_picture": ["Must be a URL returned by POST /api/upload-file/."]}`                        |
| `400`  | `gym_picture` file missing on disk    | `{"gym_picture": ["Uploaded file not found."]}`                                                 |
| `401`  | Unauthenticated                       | message: `"Authentication credentials were not provided."`                                      |
| `403`  | Caller isn't an admin                 | message: `"Admin access required."`                                                             |

---

### GET `/gyms/{uuid}/`

Retrieve one non-deleted gym.

**Permission:** `IsAuthenticatedUser` (any role, unscoped).

#### Response

`data` is a Gym object (`uuid`, `name`, `gym_picture`, `latitude`, `longitude`).

#### Example JSON Response

```json
{
  "data": {
    "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "name": "Iron Paradise",
    "gym_picture": "http://localhost:8000/media/uploads/3f9c2a7b1d4e4f6a8b0c1d2e3f4a5b6c.jpg",
    "latitude": "18.520430",
    "longitude": "73.856743"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                     | Body                                                           |
| ------ | ---------------------------------------- | -------------------------------------------------------------- |
| `401`  | Unauthenticated                          | message: `"Authentication credentials were not provided."`     |
| `404`  | Unknown or soft-deleted gym              | message: `"No Gym matches the given query."` ¹                 |
| `404`  | `uuid` isn't a valid UUID                | message: `"Not found."` ¹                                      |

¹ The 404 text comes from DRF's handling of Django's `Http404`. With `djangorestframework==3.16.0`, the Django message (`"No <Model> matches the given query."`) is forwarded when the lookup runs and misses. A malformed UUID raises a bare `Http404` inside DRF's `get_object_or_404`, which yields `"Not found."`. This wasn't run against a live server. The same applies to every `404` in Sections 2 and 3.

---

### PUT `/gyms/{uuid}/`

Full update of a gym. `updated_by` is set to the caller.

**Permission:** `IsAdminOrGymOwner`. Admin: any non-deleted gym. Gym owner: only their own gym (`uuid == gym_details_id`). Any other `uuid` returns `404` (not `403`). Trainers and members get `403`.

#### Request

| Field         | Type              | Required | Description                                            |
| ------------- | ----------------- | -------- | ------------------------------------------------------ |
| `name`        | string            | Yes      | Max 255 chars                                          |
| `gym_picture` | string \| null    | No       | Upload URL (see `POST /gyms/`), or `null` to clear. Omitting it leaves it unchanged. |
| `latitude`    | decimal \| string | Yes      | Not `null`                                             |
| `longitude`   | decimal \| string | Yes      | Not `null`                                             |

#### Response

`200 OK`. `data` is the updated Gym object (absolute image URL).

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
  "data": {
    "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "name": "Renamed Gym",
    "gym_picture": null,
    "latitude": "18.520430",
    "longitude": "73.856743"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                  | Body                                                             |
| ------ | ----------------------------------------------------- | ---------------------------------------------------------------- |
| `400`  | Missing `name`/`latitude`/`longitude`, `null` location, bad decimals, bad `gym_picture` | Field-error dict (same messages as `POST /gyms/`) |
| `401`  | Unauthenticated                                       | message: `"Authentication credentials were not provided."`       |
| `403`  | Caller is a trainer or member                         | message: `"Admin or Gym Owner access required."`                 |
| `404`  | Gym is soft-deleted, doesn't exist, or (for a gym owner) isn't their own gym | message: `"No Gym matches the given query."` |

---

### POST `/gyms/{uuid}/update/`

Partial update of a gym, implemented as a `POST` detail action that calls `partial_update()`. Send only the fields you want to change. `latitude`/`longitude` may be omitted or changed, but an explicit `null` is rejected.

**Permission:** Same as `PUT` (`IsAdminOrGymOwner`, and a gym owner is limited to their own gym).

#### Request

| Field         | Type              | Required | Description                                  |
| ------------- | ----------------- | -------- | -------------------------------------------- |
| `name`        | string            | No       | Max 255 chars, not blank                     |
| `gym_picture` | string \| null    | No       | Upload URL, or `null` to clear               |
| `latitude`    | decimal \| string | No       | Not `null`                                   |
| `longitude`   | decimal \| string | No       | Not `null`                                   |

#### Response

`200 OK`. `data` is the updated Gym object.

#### Example JSON Request

```json
{
  "latitude": "19.076090",
  "longitude": "72.877426"
}
```

#### Example JSON Response

```json
{
  "data": {
    "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "name": "Iron Paradise",
    "gym_picture": null,
    "latitude": "19.076090",
    "longitude": "72.877426"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                            | Body                                                              |
| ------ | ----------------------------------------------- | ----------------------------------------------------------------- |
| `400`  | `latitude`/`longitude` sent as `null`           | `{"latitude": ["This field may not be null."], "longitude": ["This field may not be null."]}` |
| `400`  | Other field validation (see `POST /gyms/`)      | Field-error dict                                                  |
| `401`  | Unauthenticated                                 | message: `"Authentication credentials were not provided."`        |
| `403`  | Trainer or member                               | message: `"Admin or Gym Owner access required."`                  |
| `404`  | Not found, or a gym owner targeting another gym | message: `"No Gym matches the given query."`                      |

---

### DELETE `/gyms/{uuid}/`

**Soft delete.** Calls `Gym.soft_delete()` (`core.models.BaseModel`), which sets `is_deleted = true`, `deleted_at = now`, and `updated_by = caller`.

**Permission:** `IsAdmin`. Only non-deleted gyms can be targeted.

**Side effects:** None beyond the gym row. The owner's `gym_details` FK is left pointing at the deleted gym, so their `gym_uuid` is unchanged. The gym disappears from `GET /gyms/` and `GET /gyms/{uuid}/` (which returns `404`), and the owner can no longer edit it (`404`). Owners, trainers and members are **not** disabled or deleted.

#### Response

`204 No Content`. `ResponseRenderer` still runs on `None` data, so the body the code produces is `{"data": null, "message": "", "status": 204, "time": "..."}`. Don't rely on a body for `204`.

#### Error Responses

| Status | When                             | Body                                                        |
| ------ | -------------------------------- | ----------------------------------------------------------- |
| `401`  | Unauthenticated                  | message: `"Authentication credentials were not provided."`  |
| `403`  | Caller isn't an admin            | message: `"Admin access required."`                         |
| `404`  | Unknown or already soft-deleted  | message: `"No Gym matches the given query."`                |

---

### POST `/gyms/{uuid}/enable/`

Restore a soft-deleted gym. Sets `is_deleted = false`, `deleted_at = null`, and `updated_by = caller`. It works on any gym, deleted or not (there's no "already enabled" check), so calling it on an active gym just touches `updated_by`/`updated_at`. No request body.

**Permission:** `IsAdmin`. Queryset is `Gym.objects.all()`, which includes deleted gyms.

#### Response

`200 OK`. `data` is the Gym object, serialized **without** request context, so `gym_picture` is a relative path (`/media/uploads/...`) rather than an absolute URL.

#### Example JSON Response

```json
{
  "data": {
    "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "name": "Iron Paradise",
    "gym_picture": "/media/uploads/3f9c2a7b1d4e4f6a8b0c1d2e3f4a5b6c.jpg",
    "latitude": "18.520430",
    "longitude": "73.856743"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                     | Body                                                        |
| ------ | ------------------------ | ----------------------------------------------------------- |
| `401`  | Unauthenticated          | message: `"Authentication credentials were not provided."`  |
| `403`  | Caller isn't an admin    | message: `"Admin access required."`                         |
| `404`  | Gym doesn't exist at all | message: `"No Gym matches the given query."`                |

---

## 3. User Management

Admin management of gym owners, and gym-owner management of their own trainers and members. All three resources are `CustomUser` rows (table `users`) distinguished by `user_type`.

**Router:** `accounts/urls_users.py`, a DRF `DefaultRouter` mounted at `/users/`:

| Prefix                   | ViewSet            | `basename`  |
| ------------------------ | ------------------ | ----------- |
| `/users/gym-owners/`     | `GymOwnerViewSet`  | `gym-owner` |
| `/users/trainers/`       | `TrainerViewSet`   | `trainer`   |
| `/users/members/`        | `MemberViewSet`    | `member`    |

`DefaultRouter` also serves a browsable API root at `GET /users/`, which lists links to the three prefixes. It uses the global `IsAuthenticated` permission.

All three are `BaseModelViewSet` subclasses, which exposes the following routes. Lookup is the user's `uuid`.

| Route                                  | Method   | Action                    | Gym owners | Trainers | Members |
| -------------------------------------- | -------- | ------------------------- | ---------- | -------- | ------- |
| `/users/<res>/`                        | `GET`    | `list`                    | Yes        | Yes      | Yes     |
| `/users/<res>/`                        | `POST`   | `create`                  | Yes        | Yes      | Yes     |
| `/users/<res>/{uuid}/`                 | `GET`    | `retrieve`                | Yes        | Yes      | Yes     |
| `/users/<res>/{uuid}/`                 | `PUT`    | `update`                  | Yes        | Yes      | Yes     |
| `/users/<res>/{uuid}/`                 | `PATCH`  | `partial_update`          | **405**    | **405**  | **405** |
| `/users/<res>/{uuid}/`                 | `DELETE` | `destroy` (soft delete)   | Yes        | Yes      | Yes     |
| `/users/<res>/{uuid}/update/`          | `POST`   | `partial_update_via_post` | Yes        | Yes      | Yes     |
| `/users/<res>/{uuid}/disable/`         | `POST`   | `disable`                 | Yes        | Yes      | Yes     |
| `/users/<res>/{uuid}/enable/`          | `POST`   | `enable`                  | Yes        | Yes      | Yes     |
| `/users/members/{uuid}/assign-trainer/`| `POST`   | `assign_trainer`          | —          | —        | Yes     |

`PATCH` returns `405` with message `Method "PATCH" not allowed.`. Use `POST .../update/` for partial updates.

**Response envelope:** same as [Section 2](#2-gym-master): `{"data", "message", "status", "time"}`, plus `count`/`next`/`previous` on lists. Field-validation `400`s put the error dict in both `data` and `message`. Errors with a `detail` key put it in `message` with `data: null`.

**Common query parameters (list only):**

| Param       | Description                                                                                               |
| ----------- | --------------------------------------------------------------------------------------------------------- |
| `page`      | Page number (`CustomPagination`). Out of range returns `404` with `"Invalid page."`                       |
| `page_size` | Default `20`, max `100`                                                                                   |
| `search`    | `SearchFilter`, case-insensitive partial match on `first_name`, `last_name`, `phone_number`             |
| `ordering`  | Allowed: `first_name`, `last_name`, `created_at` (prefix `-` for descending). Default: `-created_at`.   |
| `status`    | Exact filter (`DjangoFilterBackend`): `active` \| `disabled` \| `suspended` \| `deleted`. Invalid values return `400` `{"status": ["Select a valid choice. <value> is not one of the available choices."]}`. |
| `gender`    | **Members only.** `male` \| `female` \| `other`                                                          |
| `trainer`   | **Members only.** Trainer user UUID. Validated against every `user_type=trainer` user (any gym, including soft-deleted). An unknown UUID returns `400` `{"trainer": ["Select a valid choice. That choice is not one of the available choices."]}`. |

**Soft-deleted users are never listed or addressable.** Every queryset uses `CustomUser.active_objects` (`is_deleted=False`). `?status=deleted` therefore only matches users whose `status` was set to `deleted` by a `PUT`/`update/` without actually being soft-deleted (see below).

**Common behaviors and side effects:**

- **Soft delete** (`DELETE`) calls `CustomUser.soft_delete()`: `is_deleted = true`, `status = "deleted"`, `deleted_at = now`, `updated_by = caller`. `is_active` is **not** changed. Nothing cascades:
  - Deleting a gym owner leaves their trainers, members, `Gym` record and memberships untouched.
  - Deleting a trainer leaves members' `trainer_id` pointing at the deleted trainer.
  - There's **no API to restore** a soft-deleted user. `enable` only sees non-deleted users.
- **Disable/enable** only set `status` (`disabled` / `active`) plus `updated_by`/`updated_at`. They don't cascade (disabling a gym owner doesn't disable their trainers or members) and don't touch `is_deleted`.
- **Login vs. existing tokens:** `POST /auth/login/` rejects `disabled`, `suspended` and `deleted` users. However, JWT authentication uses simplejwt's `default_user_authentication_rule`, which only checks `is_active`, and the permission classes only check `user_type`. **An already-issued access token for a disabled or deleted user keeps working until it expires** (default 24 h). This is based on the configured settings and wasn't run live.
- **Phone uniqueness:** On `create`, each viewset first checks `CustomUser.objects` (**including soft-deleted users**) and returns `409` `"This phone number is already registered."` before the serializer runs. So a deleted user's number can't be reused. The phone number is otherwise free text (max 15 chars, no format validation).
- **Password rules** (`_validate_password_strength`, on create and on trainer/member password change). Every failing rule is returned in one list:
  - `"Password must be at least 8 characters long."`
  - `"Password must contain at least one uppercase letter."`
  - `"Password must contain at least one lowercase letter."`
  - `"Password must contain at least one digit."`
  - `"Password must contain at least one special character."`

  The password is hashed with `set_password()` and is never returned.
- **`gym_id` vs `gym_uuid`:** On trainer and member responses, `gym_id` is the **gym owner's user UUID** (`CustomUser.gym` FK), **not** the `Gym` master record's `uuid`. The `Gym` master UUID is exposed only as `gym_uuid` on gym-owner responses.
- **Model validation:** Create and update serializers call `full_clean()` before saving, which runs `CustomUser._validate_relationships()`. Its errors surface as `400` with `{"__all__": ["..."]}`, for example `"Trainer must belong to the same gym as the member."`. The serializer-level checks normally catch these first.
- **Images:** `profile_picture` accepts only a URL returned by `POST /api/upload-file/` (or `null`). The error messages are the same as for `gym_picture` in Section 2. The `disable`, `enable` and `assign-trainer` actions return it as a relative `/media/...` path; other endpoints return an absolute URL.

---

### GET `/users/gym-owners/`

List non-deleted gym owners, each annotated with `trainer_count` and `member_count`: the number of non-deleted trainers and members (any `status`) whose `gym` is this owner.

**Permission:** `IsAdmin` (class-level `permission_classes` for the whole `GymOwnerViewSet`).

**Query params:** `page`, `page_size`, `search`, `ordering`, `status`.

#### Response

Paginated list. Each item is a **Gym-owner object** (`GymOwnerDetailSerializer`):

| Field              | Type            | Description                                                                 |
| ------------------ | --------------- | --------------------------------------------------------------------------- |
| `uuid`             | UUID            | User identifier                                                             |
| `phone_number`     | string          | Login phone number                                                          |
| `first_name`       | string          | First name                                                                  |
| `last_name`        | string          | Last name                                                                   |
| `date_of_birth`    | date \| null    | `YYYY-MM-DD`                                                                |
| `age`              | integer \| null | Computed from `date_of_birth`                                               |
| `gender`           | string          | `male` \| `female` \| `other` \| `""`                                       |
| `profile_picture`  | string \| null  | Absolute image URL                                                          |
| `user_type`        | string          | Always `gym_owner`                                                          |
| `status`           | string          | `active` \| `disabled` \| `suspended` \| `deleted`                          |
| `gym_uuid`         | UUID \| null    | UUID of the linked `Gym` master record (`gym_details_id`)                   |
| `trainer_limit`    | integer         | Max non-deleted trainers this owner may create (default `5`)                |
| `trainer_count`    | integer         | Non-deleted trainers in this gym                                            |
| `member_count`     | integer         | Non-deleted members in this gym                                             |
| `membership_start` | date \| null    | Gym owner's platform membership start                                       |
| `membership_end`   | date \| null    | Gym owner's platform membership end                                         |
| `created_at`       | datetime        | ISO 8601, UTC (`Z`)                                                          |

`membership_status`, `membership_plan`, `experience_level`, `gym`, `trainer` and the audit fields are **not** returned.

#### Example JSON Response

```json
{
  "data": [
    {
      "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "phone_number": "9876543210",
      "first_name": "Raj",
      "last_name": "Sharma",
      "date_of_birth": "1985-03-20",
      "age": 41,
      "gender": "male",
      "profile_picture": null,
      "user_type": "gym_owner",
      "status": "active",
      "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
      "trainer_limit": 5,
      "trainer_count": 3,
      "member_count": 42,
      "membership_start": "2026-09-01",
      "membership_end": "2026-09-30",
      "created_at": "2026-09-01T08:30:00.000000Z"
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123",
  "count": 1,
  "next": null,
  "previous": null
}
```

#### Error Responses

| Status | When                  | Body                                                        |
| ------ | --------------------- | ----------------------------------------------------------- |
| `400`  | Invalid `status` filter | `{"status": ["Select a valid choice. ..."]}`              |
| `401`  | Unauthenticated       | message: `"Authentication credentials were not provided."`  |
| `403`  | Caller isn't an admin | message: `"Admin access required."`                         |
| `404`  | `page` out of range   | message: `"Invalid page."`                                  |

---

### POST `/users/gym-owners/`

Create a gym owner account, together with its `Gym` master record, in one transaction.

**Permission:** `IsAdmin`

**Side effects (`GymOwnerCreateSerializer.create`, inside `transaction.atomic()`):**
1. Creates a `Gym` with `name = gym_name`, `latitude = gym_latitude`, `longitude = gym_longitude`, and `created_by`/`updated_by` set to the admin.
2. Creates the user with `user_type = gym_owner`, `gym_details` = that gym, `created_by` = admin, `status = active` (model default), `trainer_limit = 5` (model default), and the hashed password.
3. Sets the platform membership fields: `membership_start` = today (server date), `membership_end` = `calculate_membership_end(today, membership)`, `membership_status = "active"`, `membership_plan` = the `membership` value.
4. If model validation fails, the whole transaction rolls back, so no orphan `Gym` is left.

No `Payment` or `Membership` rows are created.

`membership_end` is "same day N months later, minus one day". If that day doesn't exist in the target month, it's clamped to the month's last day before subtracting.

| `membership`  | Months | Example (start 2026-01-15) |
| ------------- | ------ | -------------------------- |
| `Monthly`     | 1      | `2026-02-14`               |
| `Quarterly`   | 3      | `2026-04-14`               |
| `Half-Yearly` | 6      | `2026-07-14`               |
| `Yearly`      | 12     | `2027-01-14`               |

#### Request

| Field             | Type              | Required | Description                                                                                     |
| ----------------- | ----------------- | -------- | ----------------------------------------------------------------------------------------------- |
| `phone_number`    | string            | Yes      | Max 15 chars, unique across **all** users including soft-deleted ones (`409` if taken)          |
| `password`        | string            | Yes      | Strong-password rules (see above)                                                               |
| `first_name`      | string            | Yes      | Max 150, not blank                                                                              |
| `last_name`       | string            | Yes      | Max 150, not blank                                                                              |
| `date_of_birth`   | date \| null      | No       | `YYYY-MM-DD`                                                                                    |
| `gender`          | string            | Yes      | `male` \| `female` \| `other`                                                                   |
| `profile_picture` | string \| null    | No       | Upload URL from `POST /api/upload-file/`                                                        |
| `gym_name`        | string            | Yes      | Max 255. Stored on the new `Gym` record                                                          |
| `gym_latitude`    | decimal \| string | Yes      | Max 9 digits, 6 decimal places                                                                   |
| `gym_longitude`   | decimal \| string | Yes      | Max 9 digits, 6 decimal places                                                                   |
| `membership`      | string            | Yes      | `Monthly` \| `Quarterly` \| `Half-Yearly` \| `Yearly` (case-sensitive)                          |

`status` is read-only here. `trainer_limit`, `membership_start` and `membership_end` can't be set on create; use `update/` afterwards.

#### Response

`201 Created`. `data` uses the create serializer's readable fields only:

| Field             | Type           | Description             |
| ----------------- | -------------- | ----------------------- |
| `uuid`            | UUID           | New user's UUID         |
| `phone_number`    | string         |                         |
| `first_name`      | string         |                         |
| `last_name`       | string         |                         |
| `date_of_birth`   | date \| null   |                         |
| `gender`          | string         |                         |
| `profile_picture` | string \| null | Absolute URL            |
| `status`          | string         | `active`                |
| `created_at`      | datetime       |                         |

`gym_uuid`, the membership dates and `trainer_limit` are **not** in the create response. Fetch `GET /users/gym-owners/{uuid}/` to get them.

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
  "data": {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "phone_number": "9876543210",
    "first_name": "Raj",
    "last_name": "Sharma",
    "date_of_birth": "1985-03-20",
    "gender": "male",
    "profile_picture": null,
    "status": "active",
    "created_at": "2026-09-23T10:15:30.123456Z"
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:15:30.130"
}
```

#### Error Responses

| Status | When                                     | Body                                                                                       |
| ------ | ---------------------------------------- | ------------------------------------------------------------------------------------------ |
| `400`  | Missing required fields                  | e.g. `{"gym_name": ["This field is required."], "gym_latitude": [...], "gym_longitude": [...], "membership": [...]}` |
| `400`  | Bad `membership`                         | `{"membership": ["\"Weekly\" is not a valid choice."]}`                                    |
| `400`  | Bad `gender`                             | `{"gender": ["\"x\" is not a valid choice."]}`                                             |
| `400`  | Weak password                            | `{"password": ["Password must contain at least one uppercase letter.", ...]}`              |
| `400`  | Bad `profile_picture` / date / decimals  | Field-error dict (messages as in Section 2)                                               |
| `401`  | Unauthenticated                          | message: `"Authentication credentials were not provided."`                                 |
| `403`  | Caller isn't an admin                    | message: `"Admin access required."`                                                        |
| `409`  | `phone_number` already exists (any user, including deleted) | message: `"This phone number is already registered."`, `data: null`          |

---

### GET `/users/gym-owners/{uuid}/`

Retrieve one gym owner. The Gym-owner object is extended with a `trainers` array listing every non-deleted trainer (any `status`) whose `gym` is this owner, ordered by `-created_at`.

**Permission:** `IsAdmin`

#### Response

All [Gym-owner object](#get-usersgym-owners) fields, plus:

| Field                      | Type            | Description                                  |
| -------------------------- | --------------- | -------------------------------------------- |
| `trainers[]`               | array           | `TrainerSummarySerializer` items             |
| `trainers[].uuid`          | UUID            | Trainer UUID                                 |
| `trainers[].name`          | string          | `get_full_name()`: `"first last"`, or the phone number if both names are blank |
| `trainers[].phone_number`  | string          |                                              |
| `trainers[].date_of_birth` | date \| null    |                                              |
| `trainers[].age`           | integer \| null |                                              |
| `trainers[].gender`        | string          |                                              |
| `trainers[].created_at`    | datetime        |                                              |

#### Example JSON Response

```json
{
  "data": {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "phone_number": "9876543210",
    "first_name": "Raj",
    "last_name": "Sharma",
    "date_of_birth": "1985-03-20",
    "age": 41,
    "gender": "male",
    "profile_picture": null,
    "user_type": "gym_owner",
    "status": "active",
    "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "trainer_limit": 5,
    "trainer_count": 1,
    "member_count": 0,
    "membership_start": "2026-09-01",
    "membership_end": "2026-09-30",
    "created_at": "2026-09-01T08:30:00.000000Z",
    "trainers": [
      {
        "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "Priya Nair",
        "phone_number": "9000000001",
        "date_of_birth": "1995-07-12",
        "age": 31,
        "gender": "female",
        "created_at": "2026-09-02T09:00:00.000000Z"
      }
    ]
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                       | Body                                                   |
| ------ | ------------------------------------------ | ------------------------------------------------------ |
| `401`  | Unauthenticated                            | message: `"Authentication credentials were not provided."` |
| `403`  | Caller isn't an admin                      | message: `"Admin access required."`                    |
| `404`  | Not a non-deleted `gym_owner`              | message: `"No CustomUser matches the given query."`    |

---

### PUT `/users/gym-owners/{uuid}/`

Full update of a gym owner (`GymOwnerDetailSerializer`). `updated_by` is set to the admin. The serializer's `update()` assigns each validated field, runs `full_clean()`, then saves.

**Permission:** `IsAdmin`

#### Request

| Field              | Type           | Required | Description                                                                                          |
| ------------------ | -------------- | -------- | ---------------------------------------------------------------------------------------------------- |
| `phone_number`     | string         | **Yes**  | Max 15. Must stay unique (the model's `UniqueValidator` checks all users, including soft-deleted)  |
| `first_name`       | string         | No       | Max 150, blank allowed                                                                               |
| `last_name`        | string         | No       | Max 150, blank allowed                                                                               |
| `date_of_birth`    | date \| null   | No       | `YYYY-MM-DD`                                                                                         |
| `gender`           | string         | No       | `male` \| `female` \| `other` \| `""`                                                                |
| `profile_picture`  | string \| null | No       | Upload URL, or `null` to clear                                                                       |
| `status`           | string         | No       | `active` \| `disabled` \| `suspended` \| `deleted`. **Caveat:** writing `deleted` here does **not** set `is_deleted`, so the user stays listed and addressable, but login is blocked. Use `DELETE` for a real soft delete. |
| `trainer_limit`    | integer        | No       | Min `0`                                                                                              |
| `membership_start` | date \| null   | No       | `YYYY-MM-DD`. No ordering check against `membership_end`                                             |
| `membership_end`   | date \| null   | No       | `YYYY-MM-DD`                                                                                         |

Only `phone_number` is required on `PUT`. Every other field is optional, and omitted fields keep their current values. Read-only and ignored if sent: `uuid`, `user_type`, `created_at`, `age`, `gym_uuid`, `trainer_count`, `member_count`. There's **no** `password` field: a gym owner's password can't be changed through this API (other than by the owner via `/auth/` change-password). `gym_name`, `membership`, `gym_details`, `membership_status` and `membership_plan` can't be changed here either. Unknown fields are silently ignored.

#### Response

`200 OK`. `data` is the Gym-owner object (with `trainer_count`/`member_count`, but no `trainers` array).

#### Example JSON Request

```json
{
  "phone_number": "9876543210",
  "first_name": "Rajesh",
  "last_name": "Sharma",
  "status": "active",
  "trainer_limit": 10,
  "membership_start": "2026-09-01",
  "membership_end": "2026-12-31"
}
```

#### Example JSON Response

```json
{
  "data": {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "phone_number": "9876543210",
    "first_name": "Rajesh",
    "last_name": "Sharma",
    "date_of_birth": "1985-03-20",
    "age": 41,
    "gender": "male",
    "profile_picture": null,
    "user_type": "gym_owner",
    "status": "active",
    "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "trainer_limit": 10,
    "trainer_count": 1,
    "member_count": 0,
    "membership_start": "2026-09-01",
    "membership_end": "2026-12-31",
    "created_at": "2026-09-01T08:30:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                     | Body                                                                   |
| ------ | ---------------------------------------- | ---------------------------------------------------------------------- |
| `400`  | `phone_number` missing on `PUT`          | `{"phone_number": ["This field is required."]}`                        |
| `400`  | `phone_number` belongs to another user   | `{"phone_number": ["User with this phone number already exists."]}` (the model's unique message; this path returns `400`, not `409`) |
| `400`  | `trainer_limit` < 0                      | `{"trainer_limit": ["Ensure this value is greater than or equal to 0."]}` |
| `400`  | Invalid `status`/`gender` choice, date, image URL | Field-error dict                                              |
| `401`  | Unauthenticated                          | message: `"Authentication credentials were not provided."`             |
| `403`  | Caller isn't an admin                    | message: `"Admin access required."`                                    |
| `404`  | Not a non-deleted gym owner              | message: `"No CustomUser matches the given query."`                    |

---

### POST `/users/gym-owners/{uuid}/update/`

Partial update of a gym owner. It takes the same fields as `PUT`, but all are optional, including `phone_number`. This is the usual way for an admin to override `trainer_limit` on its own.

**Permission:** `IsAdmin`

#### Request

Any subset of the `PUT` fields: `phone_number`, `first_name`, `last_name`, `date_of_birth`, `gender`, `profile_picture`, `status`, `trainer_limit`, `membership_start`, `membership_end`. Validation rules are the same as for `PUT`.

#### Response

`200 OK`. `data` is the Gym-owner object.

#### Example JSON Request

```json
{
  "trainer_limit": 10
}
```

#### Example JSON Response

```json
{
  "data": {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "phone_number": "9876543210",
    "first_name": "Raj",
    "last_name": "Sharma",
    "date_of_birth": "1985-03-20",
    "age": 41,
    "gender": "male",
    "profile_picture": null,
    "user_type": "gym_owner",
    "status": "active",
    "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "trainer_limit": 10,
    "trainer_count": 1,
    "member_count": 0,
    "membership_start": "2026-09-01",
    "membership_end": "2026-09-30",
    "created_at": "2026-09-01T08:30:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

Same as `PUT`, except that a missing `phone_number` isn't an error. Reusing another user's number returns `400` `{"phone_number": ["User with this phone number already exists."]}` (covered by `test_admin_cannot_reuse_phone_number_for_gym_owner`).

---

### DELETE `/users/gym-owners/{uuid}/`

Soft-delete a gym owner: `is_deleted = true`, `status = "deleted"`, `deleted_at = now`, `updated_by = admin`.

**Permission:** `IsAdmin`

**Side effects:** None beyond the owner row. Their `Gym` record stays active, and their trainers, members and memberships are **not** deleted or disabled. Those trainers and members still point at the deleted owner through `gym_id`. There's no API to undo this.

#### Response

`204 No Content` (the renderer still emits `{"data": null, "message": "", "status": 204, "time": ...}`).

#### Error Responses

| Status | When                            | Body                                                   |
| ------ | ------------------------------- | ------------------------------------------------------ |
| `401`  | Unauthenticated                 | message: `"Authentication credentials were not provided."` |
| `403`  | Caller isn't an admin           | message: `"Admin access required."`                    |
| `404`  | Not a non-deleted gym owner     | message: `"No CustomUser matches the given query."`    |

---

### POST `/users/gym-owners/{uuid}/disable/`

Set `status = "disabled"` (plus `updated_by`/`updated_at`). No request body. This blocks new logins but doesn't revoke existing tokens and doesn't cascade to the owner's trainers or members.

**Permission:** `IsAdmin`

#### Response

`200 OK`. `data` is the Gym-owner object, with `trainer_count`/`member_count` included and `profile_picture` as a relative path.

#### Example JSON Response

```json
{
  "data": {
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "phone_number": "9876543210",
    "first_name": "Raj",
    "last_name": "Sharma",
    "date_of_birth": "1985-03-20",
    "age": 41,
    "gender": "male",
    "profile_picture": "/media/uploads/9a8b7c6d5e4f40312a1b2c3d4e5f6a7b.png",
    "user_type": "gym_owner",
    "status": "disabled",
    "gym_uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
    "trainer_limit": 5,
    "trainer_count": 1,
    "member_count": 0,
    "membership_start": "2026-09-01",
    "membership_end": "2026-09-30",
    "created_at": "2026-09-01T08:30:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                        | Body                                                   |
| ------ | --------------------------- | ------------------------------------------------------ |
| `401`  | Unauthenticated             | message: `"Authentication credentials were not provided."` |
| `403`  | Caller isn't an admin       | message: `"Admin access required."`                    |
| `404`  | Not a non-deleted gym owner | message: `"No CustomUser matches the given query."`    |

---

### POST `/users/gym-owners/{uuid}/enable/`

Set `status = "active"`. No request body. This works from any non-deleted status (`disabled`, `suspended`, or a `deleted` status written via update) but **can't** restore a soft-deleted owner (`404`).

**Permission:** `IsAdmin`

#### Response

`200 OK`. `data` is the Gym-owner object with `"status": "active"`. The shape is identical to `disable/` above.

#### Error Responses

Same as `disable/`.

---

### GET `/users/trainers/`

List non-deleted trainers (any `status`).

**Permission:** `IsAdminOrGymOwner`. **Scoping:** Admin sees every trainer in every gym. Gym owner sees only trainers with `gym = self`.

**Query params:** `page`, `page_size`, `search`, `ordering`, `status`.

#### Response

Paginated list of **Trainer objects** (`TrainerDetailSerializer`):

| Field             | Type            | Description                                           |
| ----------------- | --------------- | ----------------------------------------------------- |
| `uuid`            | UUID            | Trainer UUID                                          |
| `phone_number`    | string          |                                                       |
| `first_name`      | string          |                                                       |
| `last_name`       | string          |                                                       |
| `date_of_birth`   | date \| null    |                                                       |
| `age`             | integer \| null | Computed                                              |
| `gender`          | string          | `male` \| `female` \| `other` \| `""`                 |
| `profile_picture` | string \| null  | Absolute image URL                                    |
| `user_type`       | string          | Always `trainer`                                      |
| `status`          | string          | `active` \| `disabled` \| `suspended` \| `deleted`    |
| `gym_id`          | UUID \| null    | The **gym owner's user UUID** (not the `Gym` master UUID) |
| `created_at`      | datetime        |                                                       |

`experience_level` is **not** returned, even though it's accepted on create.

#### Example JSON Response

```json
{
  "data": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "phone_number": "9000000001",
      "first_name": "Priya",
      "last_name": "Nair",
      "date_of_birth": "1995-07-12",
      "age": 31,
      "gender": "female",
      "profile_picture": null,
      "user_type": "trainer",
      "status": "active",
      "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "created_at": "2026-09-02T09:00:00.000000Z"
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123",
  "count": 1,
  "next": null,
  "previous": null
}
```

#### Error Responses

| Status | When                        | Body                                                   |
| ------ | --------------------------- | ------------------------------------------------------ |
| `400`  | Invalid `status` filter     | `{"status": ["Select a valid choice. ..."]}`           |
| `401`  | Unauthenticated             | message: `"Authentication credentials were not provided."` |
| `403`  | Trainer or member           | message: `"Admin or Gym Owner access required."`       |
| `404`  | `page` out of range         | message: `"Invalid page."`                             |

---

### POST `/users/trainers/`

Create a trainer in the requesting gym owner's gym. The server sets `user_type = trainer`, `gym = request.user`, `created_by = request.user`, `status = active` (default) and a hashed password.

**Permission:** `IsGymOwner` (admins get `403`).

**Order of checks in `TrainerViewSet.create`:**
1. **Duplicate phone:** `409` if `phone_number` exists on any user, including soft-deleted ones.
2. **Trainer limit:** `400` if the owner already has `>= trainer_limit` non-deleted trainers. Disabled and suspended trainers **do** count; soft-deleted ones don't. `trainer_limit` defaults to `5` and can only be changed by an admin via `PUT`/`POST /users/gym-owners/{uuid}/update/`. With `trainer_limit = 0`, no trainers can be created.
3. Serializer validation, then `full_clean()`, then save.

#### Request

| Field              | Type           | Required | Description                                          |
| ------------------ | -------------- | -------- | ---------------------------------------------------- |
| `phone_number`     | string         | Yes      | Max 15, globally unique (`409`)                      |
| `password`         | string         | Yes      | Strong-password rules                                |
| `first_name`       | string         | Yes      | Max 150, not blank                                   |
| `last_name`        | string         | Yes      | Max 150, not blank                                   |
| `date_of_birth`    | date \| null   | No       | `YYYY-MM-DD`                                         |
| `gender`           | string         | Yes      | `male` \| `female` \| `other`                        |
| `profile_picture`  | string \| null | No       | Upload URL                                           |
| `experience_level` | string \| null | No       | Free text, max 50                                    |

#### Response

`201 Created`. `data` is serialized with `TrainerCreateSerializer`, so it has **no** `uuid`, `age`, `user_type`, `status`, `gym_id` or `created_at`. To get the new trainer's `uuid`, list `GET /users/trainers/?search=<phone>`.

| Field              | Type           |
| ------------------ | -------------- |
| `phone_number`     | string         |
| `first_name`       | string         |
| `last_name`        | string         |
| `date_of_birth`    | date \| null   |
| `gender`           | string         |
| `profile_picture`  | string \| null |
| `experience_level` | string \| null |

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
  "data": {
    "phone_number": "9000000001",
    "first_name": "Priya",
    "last_name": "Nair",
    "date_of_birth": "1995-07-12",
    "gender": "female",
    "profile_picture": null,
    "experience_level": "3 years"
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                  | Body                                                                                   |
| ------ | ------------------------------------- | -------------------------------------------------------------------------------------- |
| `400`  | Trainer limit reached                 | `{"trainer_limit": "Trainer limit of 5 has been reached."}` (a plain string, not a list; appears in both `data` and `message`) |
| `400`  | Field validation (missing fields, weak password, bad gender, etc.) | Field-error dict                                              |
| `401`  | Unauthenticated                       | message: `"Authentication credentials were not provided."`                             |
| `403`  | Caller isn't a gym owner              | message: `"Gym Owner access required."`                                                |
| `409`  | Phone already registered              | message: `"This phone number is already registered."`                                  |

---

### GET `/users/trainers/{uuid}/`

Retrieve one trainer.

**Permission:** `IsAdminOrGymOwner`. Admin: any non-deleted trainer. Gym owner: only trainers in their own gym (others return `404`).

#### Response

`data` is a [Trainer object](#get-userstrainers).

#### Example JSON Response

```json
{
  "data": {
    "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "phone_number": "9000000001",
    "first_name": "Priya",
    "last_name": "Nair",
    "date_of_birth": "1995-07-12",
    "age": 31,
    "gender": "female",
    "profile_picture": null,
    "user_type": "trainer",
    "status": "active",
    "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "created_at": "2026-09-02T09:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                  | Body                                                   |
| ------ | ----------------------------------------------------- | ------------------------------------------------------ |
| `401`  | Unauthenticated                                       | message: `"Authentication credentials were not provided."` |
| `403`  | Trainer or member                                     | message: `"Admin or Gym Owner access required."`       |
| `404`  | Not found, soft-deleted, or (gym owner) another gym's trainer | message: `"No CustomUser matches the given query."` |

---

### PUT `/users/trainers/{uuid}/`

Full update of a trainer (`TrainerDetailSerializer`). `updated_by` is set to the gym owner. The serializer's `update()` sets the fields, hashes `password` if provided, runs `full_clean()`, then saves.

**Permission:** `IsGymOwner`. Queryset: non-deleted trainers with `gym = request.user`. Other trainers return `404`. **Admins get `403`**: they can read trainers but not modify them.

#### Request

| Field             | Type           | Required | Description                                                                                         |
| ----------------- | -------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `first_name`      | string         | No       | Max 150, blank allowed                                                                              |
| `last_name`       | string         | No       | Max 150, blank allowed                                                                              |
| `date_of_birth`   | date \| null   | No       | `YYYY-MM-DD`                                                                                        |
| `gender`          | string         | No       | `male` \| `female` \| `other` \| `""`                                                               |
| `profile_picture` | string \| null | No       | Upload URL, or `null` to clear                                                                      |
| `status`          | string         | No       | `active` \| `disabled` \| `suspended` \| `deleted` (writing `deleted` doesn't soft-delete; see the gym-owner `PUT` caveat) |
| `password`        | string         | No       | Write-only. Strong-password rules, not blank. Resets the trainer's password.                        |

No field is required, even on `PUT`. `phone_number`, `uuid`, `user_type`, `gym_id` and `created_at` are read-only, so a trainer's phone number **can't** be changed. `experience_level` isn't in this serializer, so it can't be updated here.

#### Response

`200 OK`. `data` is the Trainer object (`password` never returned).

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
  "data": {
    "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "phone_number": "9000000001",
    "first_name": "Priyanka",
    "last_name": "Nair",
    "date_of_birth": "1995-07-12",
    "age": 31,
    "gender": "female",
    "profile_picture": null,
    "user_type": "trainer",
    "status": "active",
    "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "created_at": "2026-09-02T09:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                   | Body                                                             |
| ------ | -------------------------------------- | ---------------------------------------------------------------- |
| `400`  | Weak password                          | `{"password": ["Password must be at least 8 characters long.", ...]}` |
| `400`  | Blank password                         | `{"password": ["This field may not be blank."]}`                 |
| `400`  | Invalid choice, date or image URL      | Field-error dict                                                 |
| `401`  | Unauthenticated                        | message: `"Authentication credentials were not provided."`       |
| `403`  | Caller isn't a gym owner (including admin) | message: `"Gym Owner access required."`                      |
| `404`  | Not in the caller's gym, or soft-deleted | message: `"No CustomUser matches the given query."`            |

---

### POST `/users/trainers/{uuid}/update/`

Partial update of a trainer. It takes the same fields and rules as `PUT`. This is typically used to reset a trainer's password on its own.

**Permission:** `IsGymOwner`, scoped to the caller's own gym (`404` otherwise).

#### Example JSON Request

```json
{
  "password": "NewTrainer@456"
}
```

#### Example JSON Response

```json
{
  "data": {
    "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "phone_number": "9000000001",
    "first_name": "Priya",
    "last_name": "Nair",
    "date_of_birth": "1995-07-12",
    "age": 31,
    "gender": "female",
    "profile_picture": null,
    "user_type": "trainer",
    "status": "active",
    "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "created_at": "2026-09-02T09:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

Same as `PUT /users/trainers/{uuid}/`.

---

### DELETE `/users/trainers/{uuid}/`

Soft-delete a trainer: `is_deleted = true`, `status = "deleted"`, `deleted_at = now`, `updated_by = owner`. Once deleted, the trainer no longer counts toward `trainer_limit`.

**Permission:** `IsGymOwner`, scoped to the caller's own gym.

**Side effects:** Members assigned to this trainer are **not** reassigned or cleared. Their `trainer_id` still holds the deleted trainer's UUID. The deleted trainer can't log in again, but an already-issued token keeps working until it expires (see the common notes above). No undo is available.

#### Response

`204 No Content` (the renderer still emits the envelope with `data: null`).

#### Error Responses

| Status | When                          | Body                                                   |
| ------ | ----------------------------- | ------------------------------------------------------ |
| `401`  | Unauthenticated               | message: `"Authentication credentials were not provided."` |
| `403`  | Caller isn't a gym owner      | message: `"Gym Owner access required."`                |
| `404`  | Not in the caller's gym       | message: `"No CustomUser matches the given query."`    |

---

### POST `/users/trainers/{uuid}/disable/`

Set `status = "disabled"`. No body. The trainer still counts toward `trainer_limit`, and members remain assigned.

**Permission:** `IsGymOwner`, scoped to the caller's own gym.

#### Response

`200 OK`. `data` is the Trainer object (`profile_picture` as a relative path).

#### Example JSON Response

```json
{
  "data": {
    "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "phone_number": "9000000001",
    "first_name": "Priya",
    "last_name": "Nair",
    "date_of_birth": "1995-07-12",
    "age": 31,
    "gender": "female",
    "profile_picture": null,
    "user_type": "trainer",
    "status": "disabled",
    "gym_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "created_at": "2026-09-02T09:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                          | Body                                                   |
| ------ | ----------------------------- | ------------------------------------------------------ |
| `401`  | Unauthenticated               | message: `"Authentication credentials were not provided."` |
| `403`  | Caller isn't a gym owner      | message: `"Gym Owner access required."`                |
| `404`  | Not in the caller's gym       | message: `"No CustomUser matches the given query."`    |

---

### POST `/users/trainers/{uuid}/enable/`

Set `status = "active"`. No body. This can't restore a soft-deleted trainer.

**Permission:** `IsGymOwner`, scoped to the caller's own gym.

#### Response

`200 OK`. `data` is the Trainer object with `"status": "active"`, the same shape as `disable/`.

#### Error Responses

Same as `disable/`.

---

### GET `/users/members/`

List non-deleted members (any `status`).

**Permission:** `IsAdminOrGymOwner`. **Scoping:** Admin sees every member in every gym. Gym owner sees only members with `gym = self`.

**Query params:** `page`, `page_size`, `search`, `ordering`, `status`, `gender`, `trainer` (trainer user UUID).

#### Response

Paginated list of **Member objects** (`MemberDetailSerializer`):

| Field             | Type            | Description                                              |
| ----------------- | --------------- | -------------------------------------------------------- |
| `uuid`            | UUID            | Member UUID                                              |
| `phone_number`    | string          |                                                          |
| `first_name`      | string          |                                                          |
| `last_name`       | string          |                                                          |
| `date_of_birth`   | date \| null    |                                                          |
| `age`             | integer \| null |                                                          |
| `gender`          | string          | `male` \| `female` \| `other` \| `""`                    |
| `profile_picture` | string \| null  | Absolute image URL                                       |
| `user_type`       | string          | Always `member`                                          |
| `status`          | string          | `active` \| `disabled` \| `suspended` \| `deleted`       |
| `gym_id`          | UUID \| null    | The **gym owner's user UUID**                            |
| `trainer_id`      | UUID \| null    | Assigned trainer's user UUID                             |
| `created_at`      | datetime        |                                                          |

`experience_level`, `membership_start`, `membership_end`, `membership_status` and `membership_plan` are **not** returned by this serializer.

#### Example JSON Response

```json
{
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
      "created_at": "2026-09-05T07:00:00.000000Z"
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123",
  "count": 1,
  "next": null,
  "previous": null
}
```

#### Error Responses

| Status | When                                          | Body                                                   |
| ------ | --------------------------------------------- | ------------------------------------------------------ |
| `400`  | Invalid `status` / `gender` / `trainer` filter | e.g. `{"trainer": ["Select a valid choice. That choice is not one of the available choices."]}` |
| `401`  | Unauthenticated                               | message: `"Authentication credentials were not provided."` |
| `403`  | Trainer or member                             | message: `"Admin or Gym Owner access required."`       |
| `404`  | `page` out of range                           | message: `"Invalid page."`                             |

---

### POST `/users/members/`

Create a member in the requesting gym owner's gym. The server sets `user_type = member`, `gym = request.user`, `created_by = request.user`, `status = active` (default) and a hashed password. No `Membership`, `Payment` or membership dates are created. Record those through the membership/payment endpoints (Sections 6–8).

**Permission:** `IsGymOwner` (admins get `403`).

**Order of checks:** duplicate phone (`409`), then serializer validation (including `trainer_uuid` resolution), then `full_clean()`, then save.

#### Request

| Field              | Type           | Required | Description                                                                                        |
| ------------------ | -------------- | -------- | -------------------------------------------------------------------------------------------------- |
| `phone_number`     | string         | Yes      | Max 15, globally unique (`409`)                                                                    |
| `password`         | string         | Yes      | Strong-password rules                                                                              |
| `first_name`       | string         | Yes      | Max 150, not blank                                                                                 |
| `last_name`        | string         | Yes      | Max 150, not blank                                                                                 |
| `date_of_birth`    | date \| null   | No       | `YYYY-MM-DD`                                                                                       |
| `gender`           | string         | Yes      | `male` \| `female` \| `other`                                                                      |
| `profile_picture`  | string \| null | No       | Upload URL                                                                                         |
| `experience_level` | string \| null | No       | Free text, max 50                                                                                  |
| `trainer_uuid`     | UUID \| null   | No       | Write-only. Must be a **non-deleted** trainer with `gym = request.user`. A disabled trainer is accepted, because status isn't checked. `null` or omitted means no trainer. |

#### Response

`201 Created`. `data` is serialized with `MemberCreateSerializer`, so it has **no** `uuid`, `age`, `user_type`, `status`, `gym_id`, `trainer_id` or `created_at`, and `trainer_uuid` is write-only. Find the new member via `GET /users/members/?search=<phone>`.

| Field              | Type           |
| ------------------ | -------------- |
| `phone_number`     | string         |
| `first_name`       | string         |
| `last_name`        | string         |
| `date_of_birth`    | date \| null   |
| `gender`           | string         |
| `profile_picture`  | string \| null |
| `experience_level` | string \| null |

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
  "data": {
    "phone_number": "9111111111",
    "first_name": "Amit",
    "last_name": "Verma",
    "date_of_birth": "2000-11-05",
    "gender": "male",
    "profile_picture": null,
    "experience_level": "Beginner"
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                         | Body                                                           |
| ------ | -------------------------------------------- | -------------------------------------------------------------- |
| `400`  | `trainer_uuid` not a trainer in caller's gym | `{"trainer_uuid": ["Trainer not found in this gym."]}`         |
| `400`  | `trainer_uuid` malformed                     | `{"trainer_uuid": ["Must be a valid UUID."]}`                  |
| `400`  | Other field validation                       | Field-error dict                                               |
| `401`  | Unauthenticated                              | message: `"Authentication credentials were not provided."`     |
| `403`  | Caller isn't a gym owner                     | message: `"Gym Owner access required."`                        |
| `409`  | Phone already registered                     | message: `"This phone number is already registered."`          |

---

### GET `/users/members/{uuid}/`

Retrieve one member.

**Permission:** `IsAdminOrGymOwner`. Admin: any non-deleted member. Gym owner: only members of their own gym.

#### Response

`data` is a [Member object](#get-usersmembers).

#### Example JSON Response

```json
{
  "data": {
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
    "created_at": "2026-09-05T07:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                 | Body                                                   |
| ------ | ---------------------------------------------------- | ------------------------------------------------------ |
| `401`  | Unauthenticated                                      | message: `"Authentication credentials were not provided."` |
| `403`  | Trainer or member                                    | message: `"Admin or Gym Owner access required."`       |
| `404`  | Not found, soft-deleted, or another gym's member     | message: `"No CustomUser matches the given query."`    |

---

### PUT `/users/members/{uuid}/`

Full update of a member (`MemberDetailSerializer`). `updated_by` is set to the gym owner. The serializer's `update()` sets the fields, sets `trainer_id` only if the key was sent, hashes `password` if provided, runs `full_clean()`, then saves.

**Permission:** `IsGymOwner`. Queryset: non-deleted members with `gym = request.user` (`404` otherwise). Admins get `403`.

#### Request

| Field             | Type           | Required | Description                                                                                     |
| ----------------- | -------------- | -------- | ----------------------------------------------------------------------------------------------- |
| `first_name`      | string         | No       | Max 150, blank allowed                                                                          |
| `last_name`       | string         | No       | Max 150, blank allowed                                                                          |
| `date_of_birth`   | date \| null   | No       | `YYYY-MM-DD`                                                                                    |
| `gender`          | string         | No       | `male` \| `female` \| `other` \| `""`                                                           |
| `profile_picture` | string \| null | No       | Upload URL, or `null` to clear                                                                  |
| `status`          | string         | No       | `active` \| `disabled` \| `suspended` \| `deleted` (writing `deleted` doesn't soft-delete)      |
| `trainer_id`      | UUID \| null   | No       | Reassign the trainer (must be a non-deleted trainer with `gym = request.user`), or `null` to **clear** the trainer. Omitting it leaves the trainer unchanged. |
| `password`        | string         | No       | Write-only. Strong-password rules, not blank                                                    |

No field is required. `phone_number`, `uuid`, `user_type`, `gym_id` and `created_at` are read-only. `experience_level` and the membership fields can't be edited here.

#### Response

`200 OK`. `data` is the Member object.

#### Example JSON Request

```json
{
  "first_name": "Amitabh",
  "last_name": "Verma",
  "status": "active",
  "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

#### Example JSON Response

```json
{
  "data": {
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
    "created_at": "2026-09-05T07:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                          | Body                                                             |
| ------ | --------------------------------------------- | ---------------------------------------------------------------- |
| `400`  | `trainer_id` not a trainer in the caller's gym | `{"trainer_id": ["Trainer not found in this gym."]}`            |
| `400`  | Weak or blank password                        | `{"password": [...]}`                                            |
| `400`  | Model relationship check fails                | `{"__all__": ["Trainer must belong to the same gym as the member."]}` (normally pre-empted by the `trainer_id` check) |
| `401`  | Unauthenticated                               | message: `"Authentication credentials were not provided."`       |
| `403`  | Caller isn't a gym owner                      | message: `"Gym Owner access required."`                          |
| `404`  | Not in the caller's gym                       | message: `"No CustomUser matches the given query."`              |

---

### POST `/users/members/{uuid}/update/`

Partial update of a member. It takes the same fields and rules as `PUT`. Send `trainer_id: null` to unassign the trainer, which `assign-trainer` can't do.

**Permission:** `IsGymOwner`, scoped to the caller's own gym.

#### Example JSON Request

```json
{
  "password": "NewMember@456",
  "trainer_id": null
}
```

#### Example JSON Response

```json
{
  "data": {
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
    "trainer_id": null,
    "created_at": "2026-09-05T07:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

Same as `PUT /users/members/{uuid}/`.

---

### DELETE `/users/members/{uuid}/`

Soft-delete a member: `is_deleted = true`, `status = "deleted"`, `deleted_at = now`, `updated_by = owner`.

**Permission:** `IsGymOwner`, scoped to the caller's own gym.

**Side effects:** The member's `Membership` and `Payment` rows are **not** deleted or soft-deleted, and `trainer_id` is kept. There's no undo.

#### Response

`204 No Content` (the renderer still emits the envelope with `data: null`).

#### Error Responses

| Status | When                          | Body                                                   |
| ------ | ----------------------------- | ------------------------------------------------------ |
| `401`  | Unauthenticated               | message: `"Authentication credentials were not provided."` |
| `403`  | Caller isn't a gym owner      | message: `"Gym Owner access required."`                |
| `404`  | Not in the caller's gym       | message: `"No CustomUser matches the given query."`    |

---

### POST `/users/members/{uuid}/disable/`

Set `status = "disabled"`. No body. Memberships and the trainer assignment are untouched.

**Permission:** `IsGymOwner`, scoped to the caller's own gym.

#### Response

`200 OK`. `data` is the Member object (`profile_picture` as a relative path).

#### Example JSON Response

```json
{
  "data": {
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
    "created_at": "2026-09-05T07:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                          | Body                                                   |
| ------ | ----------------------------- | ------------------------------------------------------ |
| `401`  | Unauthenticated               | message: `"Authentication credentials were not provided."` |
| `403`  | Caller isn't a gym owner      | message: `"Gym Owner access required."`                |
| `404`  | Not in the caller's gym       | message: `"No CustomUser matches the given query."`    |

---

### POST `/users/members/{uuid}/enable/`

Set `status = "active"`. No body. This can't restore a soft-deleted member.

**Permission:** `IsGymOwner`, scoped to the caller's own gym.

#### Response

`200 OK`. `data` is the Member object with `"status": "active"`, the same shape as `disable/`.

#### Error Responses

Same as `disable/`.

---

### POST `/users/members/{uuid}/assign-trainer/`

Assign or reassign a member's trainer. It sets `member.trainer` and `updated_by`, and saves only `trainer`, `updated_by` and `updated_at`. Unlike `PUT`/`update/`, this path does **not** run `full_clean()`. It can't unassign: `trainer_uuid` is required and non-null, so use `POST .../update/` with `"trainer_id": null` to clear a trainer.

**Permission:** `IsGymOwner`. The member must be non-deleted and in the caller's gym (`404` otherwise). The trainer must be a non-deleted `trainer` with `gym = request.user`. A disabled trainer is accepted, because status isn't checked.

#### Request

| Field          | Type | Required | Description                               |
| -------------- | ---- | -------- | ----------------------------------------- |
| `trainer_uuid` | UUID | Yes      | Trainer user UUID in the caller's gym     |

#### Response

`200 OK`. `data` is the Member object (serialized without request context, so `profile_picture` is a relative path).

#### Example JSON Request

```json
{
  "trainer_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

#### Example JSON Response

```json
{
  "data": {
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
    "created_at": "2026-09-05T07:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                   | Body                                                        |
| ------ | ------------------------------------------------------ | ----------------------------------------------------------- |
| `400`  | `trainer_uuid` missing                                 | `{"trainer_uuid": ["This field is required."]}`             |
| `400`  | `trainer_uuid` malformed or `null`                     | `{"trainer_uuid": ["Must be a valid UUID."]}` / `["This field may not be null."]` |
| `401`  | Unauthenticated                                        | message: `"Authentication credentials were not provided."`  |
| `403`  | Caller isn't a gym owner                               | message: `"Gym Owner access required."`                     |
| `404`  | Member not in the caller's gym                         | message: `"No CustomUser matches the given query."`         |
| `404`  | Trainer not found, soft-deleted, or in another gym     | message: `"Trainer not found in this gym."`, `data: null`   |

---

## 4. Trainer Panel

Read-only access for trainers to the members assigned to them.

**Router:** `DefaultRouter`, `register("members", TrainerMemberViewSet)` under `/trainer/`. The viewset extends `BaseModelViewSet` but sets `http_method_names = ["get", "head", "options"]`. As a result:

| Route                           | Method(s)             | Result                                                             |
| ------------------------------- | --------------------- | ------------------------------------------------------------------ |
| `/trainer/members/`             | `GET`                 | list                                                               |
| `/trainer/members/`             | `POST`                | `405`                                                              |
| `/trainer/members/{uuid}/`      | `GET`                 | retrieve                                                           |
| `/trainer/members/{uuid}/`      | `PUT`, `PATCH`, `DELETE` | `405`                                                           |
| `/trainer/members/{uuid}/update/` | `POST`              | Route is registered (inherited `partial_update_via_post` action), but always returns `405` |

**Permission:** `IsTrainer` (`user_type == trainer`) for every action. Admins, gym owners and members get `403 "Trainer access required."`.
**Queryset:** `CustomUser.active_objects.filter(user_type="member", trainer=request.user)`. This returns only non-soft-deleted members whose `trainer` FK is the calling trainer. Members with any `status` (including `disabled`) are included. Members of the same gym who aren't assigned to this trainer are excluded (covered by test `TrainerPanelTests.test_trainer_sees_only_assigned_members`).

### GET `/trainer/members/`

Paginated list of the trainer's assigned members.

**Permission:** `IsTrainer`

**Query parameters:**

| Param       | Type    | Required | Description                                                                                         |
| ----------- | ------- | -------- | --------------------------------------------------------------------------------------------------- |
| `search`    | string  | No       | `SearchFilter`: case-insensitive partial match on `first_name`, `last_name` or `phone_number`       |
| `ordering`  | string  | No       | `OrderingFilter`: `first_name`, `last_name` or `created_at` (prefix `-` for descending). Default `-created_at`. Unknown fields are ignored |
| `page`      | integer | No       | Page number (default 1)                                                                             |
| `page_size` | integer | No       | Items per page (default 20, max 100)                                                                |

No field filters (`status`, `gender`, ...) are available here.

#### Response (`MemberDetailSerializer`, per item)

| Field             | Type             | Description                                                       |
| ----------------- | ---------------- | ----------------------------------------------------------------- |
| `uuid`            | UUID             | Member ID                                                         |
| `phone_number`    | string           | Phone number                                                      |
| `first_name`      | string           | First name (may be `""`)                                          |
| `last_name`       | string           | Last name (may be `""`)                                           |
| `date_of_birth`   | string \| null   | `YYYY-MM-DD`                                                      |
| `age`             | integer \| null  | Computed from `date_of_birth`; `null` if no DOB                   |
| `gender`          | string           | `male` \| `female` \| `other` \| `""`                             |
| `profile_picture` | string \| null   | Absolute media URL                                                |
| `user_type`       | string           | Always `member`                                                   |
| `status`          | string           | `active` \| `disabled` \| `suspended` \| `deleted`                |
| `gym_id`          | UUID \| null     | UUID of the gym owner user the member belongs to                  |
| `trainer_id`      | UUID \| null     | Assigned trainer's UUID (always the caller here)                  |
| `created_at`      | datetime         | Creation timestamp                                                |

`password` is on the serializer but is write-only, so it never appears in responses. Membership-tracking fields (`membership_start`/`membership_end`/`membership_status`/`membership_plan`) are **not** part of this serializer.

#### Example JSON Response

```json
{
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
      "created_at": "2025-06-01T07:00:00.000000Z"
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123",
  "count": 1,
  "next": null,
  "previous": null
}
```

#### Error Responses

| Status | When                          | `message`                                          |
| ------ | ----------------------------- | -------------------------------------------------- |
| `403`  | Caller is not a trainer       | `"Trainer access required."`                       |
| `404`  | `page` beyond the last page   | `"Invalid page."`                                  |

---

### GET `/trainer/members/{uuid}/`

Retrieve one member assigned to the calling trainer. Uses the same scoped queryset as the list, so a member who isn't assigned to this trainer, or who is soft-deleted, returns `404`.

**Permission:** `IsTrainer`

#### Response

Same fields as the list item above (`MemberDetailSerializer`), as a single object.

#### Example JSON Response

```json
{
  "data": {
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
    "created_at": "2025-06-01T07:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                      | `message`                                    |
| ------ | --------------------------------------------------------- | -------------------------------------------- |
| `403`  | Caller is not a trainer                                   | `"Trainer access required."`                 |
| `404`  | Member not assigned to this trainer / deleted / bad UUID  | `"No CustomUser matches the given query."`   |

---

## 5. Member Panel

A single `APIView` (`MemberProfileView`, extends `BaseAPIView`/`GenericAPIView`) at `/member/profile/`. It is not a router. Only `GET` and `POST` are implemented. `PUT`, `PATCH` and `DELETE` return `405`.

**Permission:** `IsMember` (`user_type == member`). Everyone else gets `403 "Member access required."` (covered by test `test_gym_owner_cannot_access_member_panel`).
**Scope:** the view always acts on `request.user`. There is no lookup parameter.

### GET `/member/profile/`

Return the calling member's own profile.

**Permission:** `IsMember`

#### Response (`MemberProfileSerializer`)

| Field              | Type            | Description                                   |
| ------------------ | --------------- | --------------------------------------------- |
| `uuid`             | UUID            | Member ID (read-only)                         |
| `phone_number`     | string          | Phone number (read-only)                      |
| `first_name`       | string          | First name                                    |
| `last_name`        | string          | Last name                                     |
| `profile_picture`  | string \| null  | Absolute media URL                            |
| `date_of_birth`    | string \| null  | `YYYY-MM-DD` (read-only for members)          |
| `age`              | integer \| null | Computed from `date_of_birth` (read-only)     |
| `gender`           | string          | `male` \| `female` \| `other` \| `""`         |
| `experience_level` | string \| null  | Free text, max 50 chars                       |

Gym, trainer, status and membership fields are **not** returned here. Use `GET /auth/me/` for `gym_id`/`trainer_id`/`status`.

#### Example JSON Response

```json
{
  "data": {
    "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "phone_number": "9111111111",
    "first_name": "Amit",
    "last_name": "Verma",
    "profile_picture": null,
    "date_of_birth": "2000-11-05",
    "age": 25,
    "gender": "male",
    "experience_level": "Beginner"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

---

### POST `/member/profile/`

Partially update the calling member's own profile. The serializer runs with `partial=True`, so every field is optional. Read-only fields (`uuid`, `phone_number`, `date_of_birth`, `age`) and unknown keys are **silently ignored**, not rejected. `updated_by` is set to the member. No model `full_clean()` runs on this path.

**Permission:** `IsMember`

#### Request

| Field              | Type           | Required | Description / validation                                                                                   |
| ------------------ | -------------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `first_name`       | string         | No       | Max 150 chars, may be blank                                                                                |
| `last_name`        | string         | No       | Max 150 chars, may be blank                                                                                |
| `profile_picture`  | string \| null | No       | Must be a URL returned by `POST /api/upload-file/` (path under `MEDIA_URL`, file must exist). Send `null` to clear it. A raw file or `""` is rejected |
| `gender`           | string         | No       | `male` \| `female` \| `other` (blank `""` also accepted)                                                   |
| `experience_level` | string \| null | No       | Max 50 chars, nullable, may be blank                                                                       |

Accepted content types: JSON, form or multipart (global parsers). Multipart doesn't help with `profile_picture`, which only accepts a URL string.

#### Example JSON Request

```json
{
  "first_name": "Amitabh",
  "experience_level": "Intermediate"
}
```

#### Example JSON Response

`HTTP 200`, the full updated profile (same shape as GET):

```json
{
  "data": {
    "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "phone_number": "9111111111",
    "first_name": "Amitabh",
    "last_name": "Verma",
    "profile_picture": null,
    "date_of_birth": "2000-11-05",
    "age": 25,
    "gender": "male",
    "experience_level": "Intermediate"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                            | Body (error dict, in both `data` and `message`)                                          |
| ------ | ----------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `400`  | Invalid `gender`                                | `{"gender": ["\"x\" is not a valid choice."]}`                                           |
| `400`  | `profile_picture` not a string / empty string   | `{"profile_picture": ["Expected the URL returned by POST /api/upload-file/, not a raw file."]}` |
| `400`  | `profile_picture` URL not under `MEDIA_URL`     | `{"profile_picture": ["Must be a URL returned by POST /api/upload-file/."]}`             |
| `400`  | `profile_picture` file missing from storage     | `{"profile_picture": ["Uploaded file not found."]}`                                      |
| `400`  | Field too long                                  | e.g. `{"experience_level": ["Ensure this field has no more than 50 characters."]}`       |
| `403`  | Caller is not a member                          | `message: "Member access required."`                                                     |

---

## 6. Memberships

CRUD over `Membership` records (`accounts.models.Membership`). A membership links one member to a date range, plan, amount and payment mode.

**Router:** `DefaultRouter`, `register("memberships", MembershipViewSet)`, included at the site root (`path("", ...)`). The viewset extends `BaseModelViewSet` with `http_method_names = ["get", "post", "put", "delete", "head", "options"]`, so `PATCH` is **not** available (`405`). Partial updates go through `POST /{uuid}/update/`.

| Route                          | Method   | Action                                   |
| ------------------------------ | -------- | ---------------------------------------- |
| `/memberships/`                | `GET`    | list                                     |
| `/memberships/`                | `POST`   | create                                   |
| `/memberships/{uuid}/`         | `GET`    | retrieve                                 |
| `/memberships/{uuid}/`         | `PUT`    | full update                              |
| `/memberships/{uuid}/`         | `PATCH`  | `405`                                    |
| `/memberships/{uuid}/`         | `DELETE` | soft delete                              |
| `/memberships/{uuid}/update/`  | `POST`   | partial update (`partial_update_via_post`) |

Because this router is mounted at `""`, `DefaultRouter` also serves its browsable API root at `GET /` (links to `memberships` and `payments`).

**Permission:** `IsAdminOrGymOwner` for every action. Trainers and members get `403 "Admin or Gym Owner access required."`.
**Queryset scoping** (list, retrieve, update, destroy):
- **Admin:** `Membership.active_objects.all()`, i.e. every non-soft-deleted membership.
- **Gym Owner:** `Membership.active_objects.filter(member__gym=request.user)`, i.e. memberships of members whose `gym` is the caller. The member's own `is_deleted` flag is **not** checked, so memberships of soft-deleted members still appear.

**Important side-effect notes (all write actions):**
- These endpoints write **only** the `Membership` row. They do **not** update the member's denormalised `membership_start`/`membership_end`/`membership_status`/`membership_plan` fields on `CustomUser`, and they do **not** create a `Payment` row. (Compare `POST /api/payments/` in section 8, which updates the member fields.)
- No end date is auto-computed. `end_date` is always client-supplied.
- `status` is read-only and set to `active` on create. No code in the repo ever changes it to `expired` (no scheduled job or signal).
- No notification is sent. `notifications/services.py` is not called from any view in these sections.

### GET `/memberships/`

Paginated list, newest first by default.

**Permission:** `IsAdminOrGymOwner` (scoped as above)

**Query parameters:**

| Param          | Type    | Required | Description                                                                                                   |
| -------------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| `status`       | string  | No       | Exact match: `active` \| `expired`. Any other value returns `400`                                             |
| `member`       | UUID    | No       | Exact match on member UUID. Must be an existing user with `user_type == member`, or the request returns `400` |
| `payment_mode` | string  | No       | Exact match: `cash` \| `online`. Any other value returns `400`                                                |
| `ordering`     | string  | No       | `start_date`, `end_date` or `created_at` (prefix `-` for descending). Default `-created_at`                   |
| `page`         | integer | No       | Page number (default 1)                                                                                       |
| `page_size`    | integer | No       | Items per page (default 20, max 100)                                                                          |

There is no `search` parameter on this endpoint.

#### Response (`MembershipSerializer`, per item)

| Field          | Type     | Description                                           |
| -------------- | -------- | ----------------------------------------------------- |
| `uuid`         | UUID     | Membership ID (read-only)                             |
| `member`       | UUID     | Member user UUID                                      |
| `start_date`   | string   | `YYYY-MM-DD`                                          |
| `end_date`     | string   | `YYYY-MM-DD`                                          |
| `plan`         | string   | Free-text plan name (may be `""`)                     |
| `amount_paid`  | string   | Decimal serialized as a string, e.g. `"1500.00"`      |
| `payment_mode` | string   | `cash` \| `online`                                    |
| `status`       | string   | `active` \| `expired` (read-only)                     |
| `created_at`   | datetime | Read-only                                             |
| `updated_at`   | datetime | Read-only                                             |

#### Example JSON Response

```json
{
  "data": [
    {
      "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "start_date": "2026-06-01",
      "end_date": "2026-06-30",
      "plan": "Monthly",
      "amount_paid": "1500.00",
      "payment_mode": "cash",
      "status": "active",
      "created_at": "2026-06-01T08:00:00.000000Z",
      "updated_at": "2026-06-01T08:00:00.000000Z"
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123",
  "count": 1,
  "next": null,
  "previous": null
}
```

#### Error Responses

| Status | When                                  | Body                                                                                     |
| ------ | ------------------------------------- | ---------------------------------------------------------------------------------------- |
| `400`  | Invalid `status` / `payment_mode`     | e.g. `{"status": ["Select a valid choice. foo is not one of the available choices."]}`    |
| `400`  | `member` isn't an existing member UUID | `{"member": ["Select a valid choice. That choice is not one of the available choices."]}` |
| `403`  | Trainer / member caller               | `message: "Admin or Gym Owner access required."`                                         |
| `404`  | `page` out of range                   | `message: "Invalid page."`                                                               |

---

### POST `/memberships/`

Create a membership record.

**Permission:** `IsAdminOrGymOwner`. **Caution:** the code does **not** check that `member` belongs to the calling gym owner's gym. A gym owner can create a membership for any member UUID, including a member of another gym or a soft-deleted member. If the member is in another gym, the new record then falls outside the owner's own queryset and they can't read it back. Sets `created_by` and `updated_by` to the caller.

#### Request

| Field          | Type    | Required | Description / validation                                                                                                   |
| -------------- | ------- | -------- | -------------------------------------------------------------------------------------------------------------------------- |
| `member`       | UUID    | Yes      | UUID of a user with `user_type == member`. The related-field queryset is limited to members through the model's `limit_choices_to`, and it uses the default manager, so soft-deleted members are accepted |
| `start_date`   | string  | Yes      | `YYYY-MM-DD`                                                                                                               |
| `end_date`     | string  | Yes      | `YYYY-MM-DD`, must be on or after `start_date`                                                                             |
| `plan`         | string  | No       | Max 100 chars, may be blank (default `""`). Free text, not validated against any plan list                                 |
| `amount_paid`  | decimal | Yes      | Max 10 digits, 2 decimal places. **No minimum**: `0` and negative values are accepted                                      |
| `payment_mode` | string  | Yes      | `cash` \| `online` (lowercase)                                                                                             |

`status`, `uuid`, `created_at` and `updated_at` are read-only and ignored if sent.

**Overlap rule (create only):** the request is rejected if the member already has a non-soft-deleted membership with `status == active` whose range overlaps the submitted one (`existing.start_date <= end_date AND existing.end_date >= start_date`). The check covers the member's memberships across all gyms.

#### Example JSON Request

```json
{
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-07-01",
  "end_date": "2026-07-31",
  "plan": "Monthly",
  "amount_paid": "1500.00",
  "payment_mode": "cash"
}
```

#### Example JSON Response

`HTTP 201`:

```json
{
  "data": {
    "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "start_date": "2026-07-01",
    "end_date": "2026-07-31",
    "plan": "Monthly",
    "amount_paid": "1500.00",
    "payment_mode": "cash",
    "status": "active",
    "created_at": "2026-06-30T10:00:00.000000Z",
    "updated_at": "2026-06-30T10:00:00.000000Z"
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                             | Body                                                                                          |
| ------ | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `400`  | Required field missing                                           | e.g. `{"member": ["This field is required."]}`                                                |
| `400`  | `member` UUID isn't a member user (or doesn't exist)             | `{"member": ["Invalid pk \"<uuid>\" - object does not exist."]}`                              |
| `400`  | `end_date` before `start_date`                                   | `{"end_date": ["end_date must be on or after start_date."]}`                                  |
| `400`  | Overlapping active membership                                    | `{"non_field_errors": ["An active membership already exists overlapping this date range."]}`  |
| `400`  | Invalid `payment_mode`                                           | `{"payment_mode": ["\"x\" is not a valid choice."]}`                                          |
| `400`  | Bad decimal                                                      | e.g. `{"amount_paid": ["Ensure that there are no more than 2 decimal places."]}`              |
| `403`  | Trainer / member caller                                          | `message: "Admin or Gym Owner access required."`                                              |

`MembershipSerializer.validate_member` would return `"User must be of type MEMBER."`. In practice it is unreachable, because the field's queryset (DRF 3.16 applies `limit_choices_to`) already rejects non-member UUIDs with the `Invalid pk` message above.

---

### GET `/memberships/{uuid}/`

Retrieve one membership within the caller's scope.

**Permission:** `IsAdminOrGymOwner` (scoped)

#### Response

Same fields as the list item (`MembershipSerializer`).

#### Example JSON Response

```json
{
  "data": {
    "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "start_date": "2026-07-01",
    "end_date": "2026-07-31",
    "plan": "Monthly",
    "amount_paid": "1500.00",
    "payment_mode": "cash",
    "status": "active",
    "created_at": "2026-06-30T10:00:00.000000Z",
    "updated_at": "2026-06-30T10:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                | `message`                                  |
| ------ | --------------------------------------------------- | ------------------------------------------ |
| `404`  | Not in scope, soft-deleted, or bad UUID             | `"No Membership matches the given query."` |

---

### PUT `/memberships/{uuid}/`

Full update. Every writable field is required: `member`, `start_date`, `end_date`, `amount_paid` and `payment_mode` (`plan` stays optional). Sets `updated_by` to the caller.

**Permission:** `IsAdminOrGymOwner` (scoped, so the target must be visible to the caller)

Validation is the same as create (types, choices, `end_date >= start_date`), except that **the overlap check is skipped on update**. `member` can be changed to any member UUID. The gym owner's own gym isn't enforced here either. Updating does not touch the member's `CustomUser.membership_*` fields.

#### Example JSON Request

```json
{
  "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "start_date": "2026-07-01",
  "end_date": "2026-09-30",
  "plan": "Quarterly",
  "amount_paid": "4000.00",
  "payment_mode": "online"
}
```

#### Example JSON Response

```json
{
  "data": {
    "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "start_date": "2026-07-01",
    "end_date": "2026-09-30",
    "plan": "Quarterly",
    "amount_paid": "4000.00",
    "payment_mode": "online",
    "status": "active",
    "created_at": "2026-06-30T10:00:00.000000Z",
    "updated_at": "2026-07-02T11:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

Same `400` shapes as create, except the overlap error. `404` `"No Membership matches the given query."` if the membership is out of scope.

---

### POST `/memberships/{uuid}/update/`

Partial update (`partial_update_via_post` calls DRF's `partial_update`). Send only the fields you want to change. The `end_date >= start_date` check still applies, and a missing side falls back to the stored value. The overlap check is not run.

**Permission:** `IsAdminOrGymOwner` (scoped)

#### Example JSON Request

```json
{
  "end_date": "2026-08-31"
}
```

#### Example JSON Response

```json
{
  "data": {
    "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "start_date": "2026-07-01",
    "end_date": "2026-08-31",
    "plan": "Monthly",
    "amount_paid": "1500.00",
    "payment_mode": "cash",
    "status": "active",
    "created_at": "2026-06-30T10:00:00.000000Z",
    "updated_at": "2026-07-02T11:00:00.000000Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                   | Body                                                         |
| ------ | -------------------------------------- | ------------------------------------------------------------ |
| `400`  | Resulting `end_date` < `start_date`    | `{"end_date": ["end_date must be on or after start_date."]}` |
| `404`  | Out of scope / deleted                 | `message: "No Membership matches the given query."`          |

---

### DELETE `/memberships/{uuid}/`

Soft-delete (`BaseModel.soft_delete`): sets `is_deleted = true`, `deleted_at = now` and `updated_by = caller`. The row stays in the database but disappears from every `active_objects` query (these endpoints and `GET /api/payments/`). The delete does **not** cascade to `Payment` rows linked through `Payment.membership`, since `CASCADE` applies to hard deletes only. It also does not change the member's `membership_*` fields.

**Permission:** `IsAdminOrGymOwner` (scoped)

#### Response

`HTTP 204 No Content`. The view returns no data, but `ResponseRenderer` still renders an envelope (`{"data": null, "message": "", "status": 204, "time": ...}`), and the client or server may drop it because the status is 204. Treat the body as empty.

#### Error Responses

`404` `"No Membership matches the given query."` if out of scope or already deleted.

---

## 7. Payments

Read-only access to `Payment` records (`accounts.models.Payment`) **received by** the caller.

- **Admin:** payments whose payer (`paid_by`) is a **gym owner**, i.e. platform payments.
- **Gym Owner:** payments whose payer is a **member of their gym** (`paid_by.user_type == member AND paid_by.gym == caller`).

Payments with `paid_by = null` are never visible to either role. Soft-deleted payments are excluded (`Payment.active_objects`).

**Where `Payment` rows come from:** no API endpoint in this codebase creates, updates or deletes `Payment` rows. They exist only through the Django admin (`PaymentAdmin`) or direct DB/test fixtures. In particular, `POST /api/payments/` (section 8) and `POST /memberships/` do **not** create `Payment` rows. When a `Payment` is saved without one, `Payment.save()` generates `invoice_number` as `INV-<YYYYMMDD of now>-<first 6 hex chars of uuid, uppercased>`. `status` defaults to `paid` and `paid_on` defaults to now.

**Router:** `DefaultRouter`, `register("payments", PaymentViewSet)` at the site root. The viewset extends `BaseReadOnlyModelViewSet` (`http_method_names = ["get", "head", "options"]`), so only list and retrieve exist. `POST`, `PUT`, `PATCH` and `DELETE` return `405`. There is no `/update/` action.

**Permission:** `IsAdminOrGymOwner` (trainers/members get `403 "Admin or Gym Owner access required."`).

### GET `/payments/`

Paginated list, always ordered by `paid_on` descending. No `ordering` parameter is supported.

**Permission:** `IsAdminOrGymOwner` (scoped as above)

**Query parameters:**

| Param       | Type    | Required | Description                                                                                                                                                                                                         |
| ----------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status`    | string  | No       | Exact match on `status` (`paid` \| `pending` \| `overdue`). This is a manual filter with **no validation**: an unknown value returns an empty list, not a `400`                                                     |
| `search`    | string  | No       | Case-insensitive `icontains` on any of: `invoice_number`, payer full name (`first_name + " " + last_name`), the member's gym name (`paid_by.gym.gym_details.name`), the gym owner's own gym name (`paid_by.gym_details.name`) |
| `page`      | integer | No       | Page number (default 1)                                                                                                                                                                                             |
| `page_size` | integer | No       | Items per page (default 20, max 100)                                                                                                                                                                                |

#### Response (`PaymentListSerializer`, per item)

| Field             | Type           | Description                                                                                                         |
| ----------------- | -------------- | ------------------------------------------------------------------------------------------------------------------- |
| `uuid`            | UUID           | Payment ID                                                                                                          |
| `invoice_number`  | string \| null | e.g. `INV-20260715-3F2A9C`                                                                                          |
| `member_name`     | string \| null | Payer's `get_full_name()`: `"first last"` trimmed, **falls back to phone number** if both names are blank. Admin view: the gym owner's name |
| `member_phone`    | string \| null | Payer's phone number                                                                                                |
| `gym_name`        | string \| null | For a member payer: their gym owner's `gym_details.name`. For a gym-owner payer: their own `gym_details.name`. `null` if none |
| `amount`          | number         | JSON **number** (`coerce_to_string=False`), e.g. `1500.0`                                                           |
| `status`          | string         | `paid` \| `pending` \| `overdue`                                                                                    |
| `method`          | string         | `Payment.mode`: `cash` \| `online`                                                                                  |
| `membership_plan` | string \| null | `membership.plan` of the linked membership; `null` if no membership is linked                                       |
| `payment_date`    | string         | `paid_on` formatted `YYYY-MM-DD` (UTC date)                                                                         |
| `due_date`        | string \| null | `YYYY-MM-DD`                                                                                                        |

#### Example JSON Response

```json
{
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
      "payment_date": "2026-07-15",
      "due_date": null
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123",
  "count": 1,
  "next": null,
  "previous": null
}
```

#### Error Responses

| Status | When                     | `message`                                  |
| ------ | ------------------------ | ------------------------------------------ |
| `403`  | Trainer / member caller  | `"Admin or Gym Owner access required."`    |
| `404`  | `page` out of range      | `"Invalid page."`                          |

---

### GET `/payments/{uuid}/`

Retrieve one payment in detail. It uses the same `get_queryset()` as the list, so role scoping applies (`404` outside scope). If you pass `status`/`search` query params on this URL, they are applied too and can turn an in-scope payment into a `404`.

**Permission:** `IsAdminOrGymOwner` (scoped)

#### Response (`PaymentDetailSerializer`)

All list fields above, plus:

| Field        | Type          | Description                                         |
| ------------ | ------------- | --------------------------------------------------- |
| `member`     | UUID \| null  | `paid_by.uuid`: the payer (member or gym owner)     |
| `membership` | UUID \| null  | Linked membership UUID; `null` if none              |
| `paid_on`    | datetime      | Full payment timestamp (UTC)                        |
| `created_at` | datetime      | Record creation timestamp                           |
| `updated_at` | datetime      | Last update timestamp                               |

#### Example JSON Response

```json
{
  "data": {
    "uuid": "d4e5f6a7-b8c9-0123-def0-234567890123",
    "invoice_number": "INV-20260715-3F2A9C",
    "member_name": "John Doe",
    "member_phone": "9876543210",
    "gym_name": "Iron Temple",
    "amount": 1500.0,
    "status": "paid",
    "method": "cash",
    "membership_plan": "Monthly",
    "payment_date": "2026-07-15",
    "due_date": null,
    "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "membership": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "paid_on": "2026-07-15T08:00:00Z",
    "created_at": "2026-07-15T08:00:00.123456Z",
    "updated_at": "2026-07-15T08:00:00.123456Z"
  },
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                  | `message`                               |
| ------ | ----------------------------------------------------- | --------------------------------------- |
| `403`  | Trainer / member caller                               | `"Admin or Gym Owner access required."` |
| `404`  | Out of scope, soft-deleted, bad UUID, or filtered out | `"No Payment matches the given query."` |

---

## 8. Member Payments (Phase 3)

`MemberPaymentView`: a single `APIView` (extends `BaseAPIView`/`GenericAPIView`, not a router) mounted at `/api/payments/`. It implements `POST` and `GET`. `PUT`, `PATCH` and `DELETE` return `405`, and there is no `/{uuid}/` detail route.

Despite the name, this view **never touches the `Payment` model**. `POST` creates a `Membership` row and updates the member's denormalised membership fields. `GET` lists `Membership` rows. Records created here will **not** appear in `GET /payments/` (section 7). They do appear in `GET /memberships/` and `GET /api/payments/`.

**Permission:** `IsAdminOrGymOwner` (trainers/members get `403 "Admin or Gym Owner access required."`).

### POST `/api/payments/`

Record a membership "payment" for a member.

**Permission:** `IsAdminOrGymOwner`
**Member scoping:** the member is looked up as `CustomUser.active_objects.filter(uuid=member_id, user_type="member")`. For a gym owner it is further restricted to `gym=request.user`. Admins can target any non-deleted member. A soft-deleted member, a non-member UUID or another gym's member returns `404 "Member not found."`.

#### Request (`MemberPaymentSerializer`)

| Field        | Type    | Required | Description / validation                                                                               |
| ------------ | ------- | -------- | ------------------------------------------------------------------------------------------------------ |
| `member_id`  | UUID    | Yes      | Member's UUID                                                                                          |
| `date`       | string  | Yes      | `YYYY-MM-DD`. Validated but **not stored anywhere**                                                    |
| `amount`     | decimal | Yes      | Max 10 digits, 2 dp, **min `0.01`**. Stored as `Membership.amount_paid`                                |
| `mode`       | string  | Yes      | **Case-sensitive** `Cash` \| `Online`. Mapped to `cash` / `online` in `Membership.payment_mode`        |
| `start_date` | string  | Yes      | `YYYY-MM-DD`                                                                                           |
| `end_date`   | string  | Yes      | `YYYY-MM-DD`, must be on or after `start_date`                                                         |
| `plan`       | string  | No       | Max 100 chars, may be blank, default `""`. Free text (not validated against `Monthly`/`Quarterly`/...) |

**Side effects (in order, no `transaction.atomic` and no `ATOMIC_REQUESTS`):**
1. Creates a `Membership` with `member`, `start_date`, `end_date`, `amount_paid = amount`, `payment_mode = cash|online`, `plan`, `status = active`, and `created_by`/`updated_by` set to the caller. **No overlap check is run**, unlike `POST /memberships/`, so overlapping active memberships can be created here.
2. Overwrites the member's `CustomUser.membership_start = start_date`, `membership_end = end_date`, `membership_status = "active"`, `membership_plan = plan` and `updated_by = caller`. The dates are **replaced, not extended**: nothing is added to the existing end date, and no end date is computed from `plan`.
3. No `Payment` row, no invoice number and no notification. The `payment_received` template in `notifications/templates.py` exists, but no code in the repo renders it.

#### Response: known bug (still present)

`MemberPaymentResponseSerializer.amount` is declared without a `source`, and `Membership` has no `amount` attribute (only `amount_paid`). Serializing the response therefore raises `AttributeError` and the request ends in an unhandled **`HTTP 500`**. By then steps 1–2 above have **already been committed**. So a client that retries after the 500 creates a duplicate membership, and nothing blocks it because this endpoint has no overlap check.

Intended `HTTP 201` shape (`MemberPaymentResponseSerializer`), which is **not** what is returned today:

| Field         | Type    | Description                                                             |
| ------------- | ------- | ----------------------------------------------------------------------- |
| `uuid`        | UUID    | New `Membership` UUID                                                   |
| `member_id`   | UUID    | `membership.member.uuid`                                                |
| `amount`      | string  | Intended to mirror `amount_paid` (this is the field that currently crashes) |
| `amount_paid` | string  | Decimal string, e.g. `"1500.00"`                                        |
| `date`        | string  | **`start_date` echoed back**, not the submitted `date`                  |
| `start_date`  | string  | `YYYY-MM-DD`                                                            |
| `end_date`    | string  | `YYYY-MM-DD`                                                            |
| `mode`        | string  | `payment_mode`, lowercase `cash` \| `online`                            |
| `plan`        | string  | Plan name                                                               |
| `status`      | string  | Always `active`                                                         |

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

#### Example JSON Response (intended; see bug above)

```json
{
  "data": {
    "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "member_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "amount": "1500.00",
    "amount_paid": "1500.00",
    "date": "2026-07-01",
    "start_date": "2026-07-01",
    "end_date": "2026-07-31",
    "mode": "cash",
    "plan": "Monthly",
    "status": "active"
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Error Responses

| Status | When                                                          | Body                                                                         |
| ------ | ------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `400`  | Missing field                                                 | e.g. `{"member_id": ["This field is required."]}`                            |
| `400`  | `mode` not exactly `Cash`/`Online`                            | `{"mode": ["\"cash\" is not a valid choice."]}`                              |
| `400`  | `amount` < 0.01                                               | `{"amount": ["Ensure this value is greater than or equal to 0.01."]}`        |
| `400`  | `end_date` before `start_date`                                | `{"end_date": ["end_date must be on or after start_date."]}`                 |
| `400`  | Malformed UUID/date                                           | e.g. `{"member_id": ["Must be a valid UUID."]}`                              |
| `403`  | Trainer / member caller                                       | `message: "Admin or Gym Owner access required."`                             |
| `404`  | Member not found / not a member / other gym / soft-deleted    | `message: "Member not found."`                                               |
| `500`  | **Every otherwise-successful request** (see bug)              | Django 500 (HTML error page, or debug page if `DEBUG`); not wrapped by the envelope |

---

### GET `/api/payments/`

List `Membership` records (not `Payment` records).

**Permission:** `IsAdminOrGymOwner`
**Scoping:** admin gets `Membership.active_objects.all()`. A gym owner gets `Membership.active_objects.filter(member__gym=request.user)`. Order is `Membership.Meta.ordering = ["-created_at"]`.

**Query parameters:**

| Param       | Type    | Required | Description                                                                                                      |
| ----------- | ------- | -------- | ---------------------------------------------------------------------------------------------------------------- |
| `member_id` | UUID    | No       | Filter by member UUID. Not validated by a serializer: a malformed (non-UUID) value makes Django raise an unhandled `ValidationError` in the ORM, which most likely produces a `500` (not verified by a test) |
| `page_size` | integer | No       | `OptionalPagination`: a positive value (max 100) turns on pagination. Omitted/`0`/invalid returns everything      |
| `page`      | integer | No       | Only used when `page_size` is set                                                                                |

No `status`/`ordering`/`search` parameters.

#### Response

Items use `MembershipSerializer` (same fields as section 6: `uuid`, `member`, `start_date`, `end_date`, `plan`, `amount_paid`, `payment_mode`, `status`, `created_at`, `updated_at`).

#### Example JSON Response (no `page_size`, unpaginated)

```json
{
  "data": [
    {
      "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "start_date": "2026-07-01",
      "end_date": "2026-07-31",
      "plan": "Monthly",
      "amount_paid": "1500.00",
      "payment_mode": "cash",
      "status": "active",
      "created_at": "2026-06-30T10:00:00.000000Z",
      "updated_at": "2026-06-30T10:00:00.000000Z"
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123"
}
```

#### Example JSON Response (`?member_id=...&page_size=10&page=1`)

```json
{
  "data": [ { "uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012", "member": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "start_date": "2026-07-01", "end_date": "2026-07-31", "plan": "Monthly", "amount_paid": "1500.00", "payment_mode": "cash", "status": "active", "created_at": "2026-06-30T10:00:00.000000Z", "updated_at": "2026-06-30T10:00:00.000000Z" } ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:15:30.123",
  "count": 1,
  "next": null,
  "previous": null
}
```

#### Error Responses

| Status | When                                              | `message`                               |
| ------ | ------------------------------------------------- | --------------------------------------- |
| `403`  | Trainer / member caller                           | `"Admin or Gym Owner access required."` |
| `404`  | `page` out of range (only when `page_size` > 0)   | `"Invalid page."`                       |

---

### Notifications (sections 4–8)

`notifications/services.py` (`render_message`, `get_whatsapp_url`, `get_sms_text`) is **not imported or called** by any view, serializer or signal in the repo. The repo has no signals. None of the endpoints above sends or returns SMS/WhatsApp content. Templates such as `payment_received`, `membership_expiry` and `membership_expired` are defined in `notifications/templates.py` but are currently unused.

---

## 9. Attendance

Self-service attendance. A **member** or a **trainer** logs their own attendance with
their own auth token. There is no `member_id`/`user_id` in the request body: the caller
is always the subject. **No one can check anyone else in or out.** Gym owners and admins
cannot call check-in/check-out at all (`403`). A gym owner can only
[list](#get-apiattendance) the records for their gym.

> Attendance rows can also be written through the generic sync endpoint
> [`POST /api/backup/upload/`](#11-backup--sync) (model label `attendance.Attendance`,
> open to `IsAdmin | IsGymOwner | IsTrainer`). That path skips every rule in this section:
> no geofence, no duplicate check, no photo requirement. The rules below apply only to
> `/api/attendance/checkin/` and `/api/attendance/checkout/`.

**Members and trainers follow different rules:**

- A **member**'s attendance is one presence marker per day. **Members have no check-out.**
  One check-in per calendar day is the whole record. The day comes from the `timestamp`
  the client sends, evaluated in **UTC** (see *Timezones* below). `check_out`,
  `check_out_lat`, `check_out_lng`, `check_in_photo` and `check_out_photo` are always
  `null` for a member. `POST /api/attendance/checkout/` is `IsTrainer` only and returns
  `403` for a member. A second check-in on the same UTC date returns `400`. The next UTC
  date allows a new check-in.
- A **trainer**'s attendance works like shifts, with an open/close pair. Check-in fails
  if the trainer has **any** record that is still open (`check_out` is `null`), on any
  day. Check-out fails if no open record exists. There is no per-day limit, so a trainer
  can run several shifts in one day as long as each one is closed before the next starts.

**Geofence:** every check-in and check-out must be within **50 meters**
(`ATTENDANCE_RADIUS_M = 50`) of the caller's gym. The distance is the haversine
great-circle distance to the `Gym.latitude`/`Gym.longitude` of the gym the caller belongs
to (`caller.gym` → gym owner → `gym_details`). There are two failure cases, both `400`:

- The caller has no `gym`, the gym owner has no `gym_details`, or that gym's latitude or
  longitude is `null`. All three give the same message: `"Your gym has no registered
  location. Contact your gym owner."`
- The point is more than 50 m away. The message includes the rounded distance.

**Photo:** a **trainer** must send `photo` on both check-in and check-out. It is a
**URL string** returned by [`POST /api/upload-file/`](#12-utility). It is **not** a
multipart file upload: a raw file is rejected. For a **member**, `photo` is optional
and never stored. If a member does send a `photo`, it is still validated (it must be
`null` or a valid uploaded-file URL), so an invalid value returns `400` even though it
would be thrown away.

**Timezones:** the server runs with `USE_TZ = True` and `TIME_ZONE = "UTC"`.

- A `timestamp` with an offset (e.g. `+05:30`) is converted to UTC.
- A `timestamp` without an offset is treated as UTC.
- Responses always return datetimes in UTC with a `Z` suffix.
- The member "one per day" rule, the list `?date=` filter and the reports all use the
  **UTC** calendar date. For example, a check-in at `2026-06-30T01:00:00+05:30` counts
  as `2026-06-29`.

**Timestamps are client-supplied and not validated against server time.** A past or
future `timestamp` is accepted. Check-out does not check that its `timestamp` is later
than the check-in.

**Validation order:** each check stops the request at the first failure.

- Check-in: serializer fields → trainer photo → duplicate → geofence.
- Check-out: serializer fields → photo → open record → geofence.

**Soft delete:** every lookup here uses `Attendance.active_objects`, so soft-deleted
(`is_deleted=true`) records are ignored everywhere. That includes duplicate checks, the
open-shift lookup, listing and reports.

---

### POST `/api/attendance/checkin/`

Checks the authenticated member or trainer in, creating a new `Attendance` record.

**Permission:** `IsMember | IsTrainer`. The caller must be a member or a trainer, and the
record is always created for `request.user`. Gym owners and admins get `403`.

#### Request

`application/json` (form and multipart bodies are also parsed, but `photo` must still be
a URL string).

| Field       | Type                 | Required     | Description                                                                                                                                                     |
| ----------- | -------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `timestamp` | datetime (ISO-8601)  | Yes          | Check-in time. Converted to UTC (a value without an offset is treated as UTC). Stored as-is in `check_in`.                                                         |
| `lat`       | decimal              | Yes          | Latitude. At most 9 digits total and 6 decimal places (more decimal places are rejected, not rounded). There is no range check beyond the geofence.                   |
| `lng`       | decimal              | Yes          | Longitude. Same rules as `lat`.                                                                                                                                   |
| `photo`     | string (URL) \| null | Trainer only | URL returned by `POST /api/upload-file/` (it must point under `/media/`, and the file must exist). **Required for a trainer.** Optional for a member, and validated but never stored if sent. |

#### Response

`201 Created`. The payload is the `AttendanceSerializer` object, inside the envelope's `data`.

| Field             | Type                     | Description                                                                                                                                                                                      |
| ----------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `uuid`            | UUID                     | Attendance record UUID                                                                                                                                                                           |
| `user`            | UUID                     | Caller's user UUID                                                                                                                                                                               |
| `user_name`       | string                   | Caller's `first_name last_name`, trimmed. Falls back to `phone_number` if both are blank.                                                                                                        |
| `user_type`       | string                   | `member` \| `trainer`                                                                                                                                                                            |
| `check_in`        | datetime                 | Check-in time (UTC, `Z`)                                                                                                                                                                         |
| `check_out`       | datetime \| null         | Always `null` on check-in, and always `null` for a member                                                                                                                                        |
| `check_in_lat`    | string (decimal)         | Check-in latitude, returned as a string (e.g. `"19.075984"`)                                                                                                                                      |
| `check_in_lng`    | string (decimal)         | Check-in longitude, returned as a string                                                                                                                                                          |
| `check_out_lat`   | string (decimal) \| null | `null` until a trainer checks out                                                                                                                                                                |
| `check_out_lng`   | string (decimal) \| null | `null` until a trainer checks out                                                                                                                                                                |
| `check_in_photo`  | string \| null           | Trainer only. This is a **relative** media URL such as `/media/uploads/<hex>.png`, because the serializer is built without the request and cannot make an absolute URL. Always `null` for a member. |
| `check_out_photo` | string \| null           | `null` on check-in                                                                                                                                                                               |

#### Example JSON Request (member)

```json
{
  "timestamp": "2026-06-30T06:00:00Z",
  "lat": "19.075984",
  "lng": "72.877656"
}
```

#### Example JSON Request (trainer)

```json
{
  "timestamp": "2026-06-30T06:00:00Z",
  "lat": "19.075984",
  "lng": "72.877656",
  "photo": "http://localhost:8000/media/uploads/3f9c2a7be1d04c0f8a1b2c3d4e5f6a7b.png"
}
```

#### Example JSON Response (member)

```json
{
  "data": {
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
  },
  "message": "",
  "status": 201,
  "time": "2026-06-30T11:30:00.123456"
}
```

(`time` is the server's naive local `datetime.now()` and has no timezone suffix.)

#### Error Responses

For errors that carry a `detail`, the envelope's `data` is `null` and `message` holds the
detail text.

| Status | When                                                                                          | Body                                                                                                                               |
| ------ | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `400`  | A field is missing or malformed                                                               | `data` and `message` both hold the DRF field-error dict, e.g. `{"lat": ["This field is required."]}` or `{"lat": ["Ensure that there are no more than 6 decimal places."]}` |
| `400`  | `photo` is not a string (e.g. a raw multipart file) or is `""`                                | `{"photo": ["Expected the URL returned by POST /api/upload-file/, not a raw file."]}`                                               |
| `400`  | `photo` URL path is not under `/media/`                                                        | `{"photo": ["Must be a URL returned by POST /api/upload-file/."]}`                                                                  |
| `400`  | `photo` URL points to a file that doesn't exist                                                | `{"photo": ["Uploaded file not found."]}`                                                                                           |
| `400`  | Trainer sent no `photo` (or `null`)                                                            | message: `"A photo is required for check-in."`                                                                                      |
| `400`  | Trainer already has an open record (any day)                                                   | message: `"You're already checked in."`                                                                                             |
| `400`  | Member already has a check-in on the same UTC date as `timestamp`                              | message: `"You've already checked in today."`                                                                                       |
| `400`  | Caller has no gym, or the gym has no latitude/longitude                                        | message: `"Your gym has no registered location. Contact your gym owner."`                                                           |
| `400`  | Point is more than 50 m from the gym                                                           | message: `"You are <N>m away from your gym — check-in/out must be within 50m of the gym location."` (`<N>` is the distance rounded to whole meters) |
| `401`  | No or invalid bearer token                                                                     | message: `"Authentication credentials were not provided."` (or SimpleJWT's token-invalid message)                                   |
| `403`  | Caller is a gym owner or admin                                                                 | message: DRF's permission-denied text. For an `A \| B` composed permission this is expected to be DRF's default `"You do not have permission to perform this action."` rather than one of the per-class messages. Not verified against a running server. |

---

### POST `/api/attendance/checkout/`

Checks the authenticated **trainer** out of their own open record. The request needs no
id: the server closes the caller's **most recent** open record (`check_out` is `null`,
ordered by `-check_in`). **Only trainers can call this.** Members get `403` because they
have no check-out.

**Permission:** `IsTrainer`

#### Request

| Field       | Type                | Required | Description                                                                      |
| ----------- | ------------------- | -------- | -------------------------------------------------------------------------------- |
| `timestamp` | datetime (ISO-8601) | Yes      | Check-out time (converted to UTC). Not checked against `check_in`.               |
| `lat`       | decimal             | Yes      | Latitude. At most 9 digits and 6 decimal places.                                 |
| `lng`       | decimal             | Yes      | Longitude. Same rules.                                                           |
| `photo`     | string (URL)        | Yes      | URL returned by `POST /api/upload-file/`. The serializer lets it be omitted, but the view then rejects the request. |

#### Response

`200 OK`. Returns the updated record, with the same fields as the
[check-in response](#post-apiattendancecheckin). `check_out`, `check_out_lat`,
`check_out_lng` and `check_out_photo` are now filled in, and `check_out_photo` is a
relative `/media/...` URL.

#### Example JSON Request

```json
{
  "timestamp": "2026-06-30T07:30:00Z",
  "lat": "19.075984",
  "lng": "72.877656",
  "photo": "http://localhost:8000/media/uploads/8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a.png"
}
```

#### Example JSON Response

```json
{
  "data": {
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
    "check_in_photo": "/media/uploads/3f9c2a7be1d04c0f8a1b2c3d4e5f6a7b.png",
    "check_out_photo": "/media/uploads/8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a.png"
  },
  "message": "",
  "status": 200,
  "time": "2026-06-30T13:00:00.123456"
}
```

#### Error Responses

| Status | When                                                         | Body                                                                                                 |
| ------ | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| `400`  | A field is missing or malformed (including the `photo` URL errors listed under check-in) | DRF field-error dict in `data` and `message`                                                         |
| `400`  | No `photo` (or `null`)                                       | message: `"A photo is required for trainer check-out."`                                              |
| `400`  | Trainer has no open record                                   | message: `"No active check-in found."`                                                               |
| `400`  | Caller has no gym, or the gym has no location                | message: `"Your gym has no registered location. Contact your gym owner."`                            |
| `400`  | Point is more than 50 m from the gym                          | message: `"You are <N>m away from your gym — check-in/out must be within 50m of the gym location."` |
| `401`  | No or invalid token                                          | message: `"Authentication credentials were not provided."`                                          |
| `403`  | Caller is not a trainer (member, gym owner, admin)           | message: `"Trainer access required."`                                                                |

---

### GET `/api/attendance/`

Lists attendance records, newest first (`-check_in`). You can filter by user and/or date.

**Permission:** `IsGymOwner | IsTrainer | IsMember`. Admins get `403`.

- **Gym owner:** sees every non-deleted record whose user has `gym` set to this owner.
  That covers both members and trainers. Records of users who were soft-deleted are
  still included, because only the attendance row's own soft-delete is filtered.
- **Trainer / member:** sees only their own records. A trainer does **not** see their
  assigned members' attendance here. Members' visits appear only in the
  [inactive-members report](#get-apireportsinactive-members).

**Pagination is optional** (`OptionalPagination`).

- If you omit `page_size`, or pass `0`, a negative number or a non-integer, every
  matching record comes back as a plain array in `data`, with no
  `count`/`next`/`previous`.
- If you pass a positive `page_size` (capped at `100`, used with `page`), the response
  switches to the paginated envelope: `data` holds one page, and `count`, `next` and
  `previous` are added at the top level.

**Query parameters:**

| Param       | Type    | Required | Description                                                                                                                                                                                                  |
| ----------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `user_id`   | UUID    | No       | Keep records where `user.uuid` equals this value. It is applied on top of the role scope for every role. A gym owner can narrow to one member or trainer. For a trainer or member, any other UUID just returns `[]`. |
| `date`      | string  | No       | `YYYY-MM-DD`. Keeps records whose `check_in` falls on this **UTC** date.                                                                                                                                      |
| `page`      | integer | No       | Page number. Only used when `page_size` is set.                                                                                                                                                               |
| `page_size` | integer | No       | Records per page, capped at `100`. `0` or omitted returns everything.                                                                                                                                         |

`user_id` and `date` are passed straight to the ORM without validation. A malformed
UUID or date raises a Django `ValidationError` that nothing catches, which shows up as an
HTTP `500`, not a `400`.

#### Response

An array of attendance objects. The fields are the same as the
[check-in response](#post-apiattendancecheckin).

#### Example JSON Response (unpaginated)

```json
{
  "data": [
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
  ],
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Example JSON Response (`?page_size=1&page=1`)

```json
{
  "data": [
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
  ],
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456",
  "count": 14,
  "next": "http://localhost:8000/api/attendance/?page=2&page_size=1",
  "previous": null
}
```

#### Error Responses

| Status | When                                              | Body                                             |
| ------ | ------------------------------------------------- | ------------------------------------------------ |
| `401`  | No or invalid token                               | message: `"Authentication credentials were not provided."` |
| `403`  | Caller is an admin                                | DRF permission-denied message (composed permission, see check-in) |
| `404`  | `page` is out of range (only when `page_size` > 0) | message: `"Invalid page."`                       |
| `500`  | Malformed `user_id` or `date`                     | Unhandled Django `ValidationError`               |

---

## 10. Reports

All report endpoints are read-only `GET`s under `/api/reports/`. They go through the
standard envelope (`core/renderers.py::ResponseRenderer`). Each report computes its
result on every request; nothing is cached.

| Endpoint                                   | Permission              | Scope                                                                         | Paginated (optional) |
| ------------------------------------------ | ----------------------- | ----------------------------------------------------------------------------- | -------------------- |
| `/api/reports/inactive-members/`           | `IsGymOwner \| IsTrainer` | Gym owner: members of their gym. Trainer: only members assigned to them.      | Yes                  |
| `/api/reports/trainer-workload/`           | `IsGymOwner`            | Trainers of the caller's gym                                                  | Yes                  |
| `/api/reports/membership-expiry/`          | `IsGymOwner`            | Members of the caller's gym                                                   | Yes                  |
| `/api/reports/gym-subscription-expiry/`    | `IsAdmin`               | All gym owners, platform-wide                                                 | Yes                  |
| `/api/reports/revenue-summary/`            | `IsAdmin \| IsGymOwner`   | Admin: gym-owner → platform payments. Gym owner: their members' payments.     | No                   |
| `/api/reports/storage-usage/`              | `IsAdmin`               | Whole `MEDIA_ROOT`                                                            | No                   |
| `/api/reports/api-requests-today/`         | `IsAdmin`               | Whole server                                                                  | No                   |
| `/api/reports/workout-backups-count/`      | `IsAdmin`               | All users                                                                     | No                   |

**Common rules:**

- **Soft-deleted users are excluded.** User lookups use `CustomUser.active_objects`
  (`is_deleted=False`). Account `status` (`disabled`/`suspended`) is **not** checked, so
  disabled or suspended users still show up in the member, trainer and owner reports.
- **Pagination** (for the endpoints marked *Yes*) works like
  [`GET /api/attendance/`](#get-apiattendance), with the same `page`/`page_size` rules.
  The list is built in Python and then sliced. No ordering is applied, so rows come back
  in database order.
- **`days` parameter** (inactive-members, membership-expiry, gym-subscription-expiry):
  the value is read with `int(...)` and not validated further.
  - Default: `7`.
  - Negative values are accepted.
  - A non-integer value (e.g. `?days=abc`) raises an uncaught `ValueError`, which returns
    HTTP `500`.
- **"Today"** is the UTC date (`timezone.now().date()` with `TIME_ZONE = "UTC"`).
- **Errors for every report:** `401` with no or invalid token. `403` when the caller's
  role isn't allowed. A single permission class returns its own message (`"Gym Owner
  access required."`, `"Admin access required."`). An `A | B` composition returns DRF's
  permission-denied text (see [check-in](#post-apiattendancecheckin)). The paginated
  reports also return `404` / `"Invalid page."` when `page` is out of range.

---

### GET `/api/reports/inactive-members/`

Returns members whose most recent check-in is at least `days` days old, plus members who
have never checked in.

**Permission:** `IsGymOwner | IsTrainer`. Admins and members get `403`.

- **Gym owner:** every non-deleted `member` with `gym = caller`.
- **Trainer:** every non-deleted `member` with `trainer = caller`. The member's `gym`
  isn't checked in addition to this.

**Computation:**

1. `cutoff = now() - days`. This is an exact datetime, not the start of a day.
2. `last_visit` is the member's latest non-deleted `Attendance.check_in`, found with a
   subquery.
3. A member is **inactive** when they have no check-in at all, or when
   `last_visit <= cutoff`.
4. Because the timestamp is client-supplied, a check-in dated in the future makes a
   member count as active.

**Query parameters:**

| Param       | Type    | Required | Default | Description                                                                         |
| ----------- | ------- | -------- | ------- | ----------------------------------------------------------------------------------- |
| `days`      | integer | No       | `7`     | Inactivity threshold in days. Not range-checked. Non-integer values cause a `500`. |
| `page`      | integer | No       |         | Page number (only when `page_size` > 0)                                             |
| `page_size` | integer | No       | `0`     | Records per page, capped at `100`. `0` or omitted returns everything.               |

#### Request

No body.

#### Response

`data` is an array of:

| Field           | Type           | Description                                                                                                                                                         |
| --------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `member_id`     | string (UUID)  | Member UUID                                                                                                                                                         |
| `name`          | string         | `first_name last_name`, or `phone_number` if both are blank                                                                                                         |
| `last_visit`    | string \| null | UTC date (`YYYY-MM-DD`) of the latest check-in. `null` if the member never checked in.                                                                               |
| `days_inactive` | integer        | `today (UTC) − last_visit date`, in whole days. For a member who **never** checked in, this is the `days` value from the query (default `7`), not a real count. |

#### Example JSON Response

```json
{
  "data": [
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
  ],
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Error Responses

| Status | When                          | Body                                    |
| ------ | ----------------------------- | --------------------------------------- |
| `403`  | Caller is an admin or a member | DRF permission-denied message (composed) |
| `404`  | `page` is out of range        | message: `"Invalid page."`              |
| `500`  | `days` is not an integer      | Uncaught `ValueError`                   |

---

### GET `/api/reports/trainer-workload/`

Lists every non-deleted trainer in the caller's gym with the number of members assigned
to them. Trainers with no members are included with a count of `0`.

**Permission:** `IsGymOwner`. Only trainers with `gym = caller` are included.

**Query parameters:** `page`, `page_size` (optional pagination, see above).

#### Response

`data` is an array of:

| Field          | Type          | Description                                                                                                                                                                                                  |
| -------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `trainer_id`   | string (UUID) | Trainer UUID                                                                                                                                                                                                 |
| `name`         | string        | Full name, or `phone_number` if blank                                                                                                                                                                        |
| `member_count` | integer       | Count of users with `trainer = this trainer`, `user_type = member` and `is_deleted = false`. "Active" here only means not soft-deleted. It does not check `status`, `membership_status` or `membership_end`. |

#### Example JSON Response

```json
{
  "data": [
    {
      "trainer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Priya Nair",
      "member_count": 12
    },
    {
      "trainer_id": "f6a7b8c9-d0e1-2345-f012-456789012345",
      "name": "Ravi Kumar",
      "member_count": 0
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Error Responses

| Status | When                | Body                                    |
| ------ | ------------------- | --------------------------------------- |
| `403`  | Not a gym owner     | message: `"Gym Owner access required."` |
| `404`  | `page` out of range | message: `"Invalid page."`              |

---

### GET `/api/reports/membership-expiry/`

Returns members of the caller's gym whose `membership_end` is **on or before
`today + days`**.

- There is **no lower bound**. Every member whose membership has already expired is
  included, however long ago it ended.
- Members with `membership_end = null` are excluded.
- The date used is the denormalised `CustomUser.membership_end` field. The `Membership`
  table is not queried.
- `membership_status` is not considered.

**Permission:** `IsGymOwner`. Only non-deleted `member` users with `gym = caller` are
included.

**Query parameters:**

| Param       | Type    | Required | Default | Description                                            |
| ----------- | ------- | -------- | ------- | ------------------------------------------------------ |
| `days`      | integer | No       | `7`     | Look-ahead window in days. Non-integer values cause a `500`. |
| `page`      | integer | No       |         | Page number                                            |
| `page_size` | integer | No       | `0`     | Records per page, capped at `100`. `0` returns everything. |

#### Response

`data` is an array of:

| Field         | Type          | Description                                                       |
| ------------- | ------------- | ----------------------------------------------------------------- |
| `member_id`   | string (UUID) | Member UUID                                                       |
| `name`        | string        | Full name, or `phone_number` if blank                             |
| `expiry_date` | string        | `membership_end` (`YYYY-MM-DD`)                                   |
| `days_left`   | integer       | `membership_end − today (UTC)`. `0` means it expires today. Negative means it has already expired. |

#### Example JSON Response

```json
{
  "data": [
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
  ],
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Error Responses

| Status | When                     | Body                                    |
| ------ | ------------------------ | --------------------------------------- |
| `403`  | Not a gym owner          | message: `"Gym Owner access required."` |
| `404`  | `page` out of range      | message: `"Invalid page."`              |
| `500`  | `days` is not an integer | Uncaught `ValueError`                   |

---

### GET `/api/reports/gym-subscription-expiry/`

Admin only. Returns **gym owner** accounts across the whole platform whose own
subscription (`CustomUser.membership_end` on the owner) is **on or before
`today + days`**.

- As with `membership-expiry`, there is **no lower bound**, so owners whose subscription
  has already expired are always included.
- Owners with `membership_end = null` are excluded.

This is different from `membership-expiry`, which covers **member** memberships inside
one gym.

**Permission:** `IsAdmin`. Covers all non-deleted `gym_owner` users.

**Query parameters:** `days` (integer, default `7`, same rules as above), `page`,
`page_size`.

#### Response

`data` is an array of:

| Field          | Type           | Description                                                     |
| -------------- | -------------- | --------------------------------------------------------------- |
| `gym_owner_id` | string (UUID)  | Gym owner UUID                                                  |
| `name`         | string         | Owner's full name, or `phone_number` if blank                   |
| `gym_name`     | string \| null | `gym_details.name`. `null` if the owner has no linked `Gym`.    |
| `expiry_date`  | string         | `membership_end` (`YYYY-MM-DD`)                                 |
| `days_left`    | integer        | `membership_end − today (UTC)`. Negative means already expired. |

#### Example JSON Response

```json
{
  "data": [
    {
      "gym_owner_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Raj Sharma",
      "gym_name": "Iron Paradise",
      "expiry_date": "2026-07-03",
      "days_left": 3
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Error Responses

| Status | When                     | Body                                |
| ------ | ------------------------ | ----------------------------------- |
| `403`  | Not an admin             | message: `"Admin access required."` |
| `404`  | `page` out of range      | message: `"Invalid page."`          |
| `500`  | `days` is not an integer | Uncaught `ValueError`               |

---

### GET `/api/reports/revenue-summary/`

Revenue totals for the current calendar month, plus a breakdown by payment method for
the same month. Not paginated. It takes no query parameters.

**Permission:** `IsAdmin | IsGymOwner`. The base set is non-deleted `Payment` rows, scoped
by role:

- **Admin:** payments where `paid_by.user_type = gym_owner`, i.e. gym-owner → platform
  payments. Payments with `paid_by = null` are excluded.
- **Gym owner:** payments where `paid_by.user_type = member` and `paid_by.gym = caller`.

This matches the scoping of [`GET /payments/`](#7-payments).

**Computation** (all times in UTC):

- `this_month_start` is 00:00:00 UTC on the 1st of the current month, and
  `last_month_start` is 00:00:00 UTC on the 1st of the previous month.
- **This month** = `status = paid` and `paid_on >= this_month_start`. There is no upper
  bound, so a `paid` payment with a future `paid_on` also counts.
- **Last month** = `status = paid` and `last_month_start <= paid_on < this_month_start`.
- `overdue` payments are not counted anywhere in this report.

#### Response

`data` is an object:

| Field                       | Type             | Description                                                                                                                                                                                          |
| --------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `total_revenue`             | number           | Sum of `amount` for this month's `paid` payments. Returns `0.0` if there are none. Rendered as a JSON **number**, not a string: the view returns raw `Decimal`s, and DRF's JSON encoder writes them as floats. |
| `monthly_growth_percent`    | number           | `(this_month − last_month) / last_month × 100`, rounded to 1 decimal place. Can be negative. If last month is `0`, the value is `100.0` when this month is above 0, and `0.0` when both are 0. |
| `total_transactions`        | integer          | Number of this month's `paid` payments                                                                                                                                                               |
| `pending_amount`            | number           | Sum of `amount` for **all** payments with `status = pending` in scope, whatever their date. Excludes `overdue`. Returns `0.0` if there are none.                                                   |
| `method_breakdown`          | array            | One entry per payment `mode` that has paid payments this month, sorted by amount, largest first. Modes with no payments are left out, so the array can be empty.                                  |
| `method_breakdown[].method` | string           | `cash` \| `online`                                                                                                                                                                                   |
| `method_breakdown[].amount` | number           | Sum of this month's `paid` amounts for that mode                                                                                                                                                     |

#### Example JSON Response

```json
{
  "data": {
    "total_revenue": 86400.0,
    "monthly_growth_percent": 12.4,
    "total_transactions": 42,
    "pending_amount": 3200.0,
    "method_breakdown": [
      { "method": "online", "amount": 54000.0 },
      { "method": "cash", "amount": 32400.0 }
    ]
  },
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Error Responses

| Status | When                                  | Body                                     |
| ------ | ------------------------------------- | ---------------------------------------- |
| `403`  | Caller is a trainer or a member       | DRF permission-denied message (composed) |

---

### GET `/api/reports/storage-usage/`

Admin only. Returns the total size, in bytes, of every file under `MEDIA_ROOT`
(`<BASE_DIR>/media`), found by walking the directory recursively on each request. That
includes profile pictures, gym pictures, files from `/api/upload-file/` (such as
attendance photos), music files, and so on.

- Nothing is cached, so this can be slow on a large media folder.
- Files that can't be `stat`-ed are skipped.
- If `MEDIA_ROOT` doesn't exist, the result is `0`.
- Files kept in any other storage backend are not counted, because only the local
  filesystem is walked.

**Permission:** `IsAdmin`

#### Response

| Field         | Type    | Description                  |
| ------------- | ------- | ---------------------------- |
| `total_bytes` | integer | Sum of file sizes, in bytes  |

#### Example JSON Response

```json
{
  "data": { "total_bytes": 40894627840 },
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Error Responses

| Status | When         | Body                                |
| ------ | ------------ | ----------------------------------- |
| `403`  | Not an admin | message: `"Admin access required."` |

---

### GET `/api/reports/api-requests-today/`

Admin only. Returns the number of HTTP requests received so far on the current **UTC**
date. `TIME_ZONE = "UTC"`, so `timezone.localdate()` is the UTC date.

The count comes from `core.middleware.RequestCounterMiddleware`, which keeps one
`DailyRequestCount` row per date and adds 1 with `F("count") + 1` on every request
(this stays correct across multiple workers).

- **Counted:** every request whose path does **not** start with `/admin/`, `/media/`,
  `/static/`, `/schema/` or `/docs/`. That means all API routes (`/auth/`, `/gyms/`,
  `/users/`, `/api/...`, and so on), whether or not the request is authenticated. It
  includes `401`, `403` and `404` responses, unknown URLs, and this report call itself.
- **Probably not counted:** CORS preflight `OPTIONS` requests. `CorsMiddleware` sits
  earlier in the middleware stack and normally answers them before this middleware runs.
  This is how django-cors-headers behaves, not something this repo checks.

**Permission:** `IsAdmin`

#### Response

| Field   | Type    | Description                                                                              |
| ------- | ------- | ---------------------------------------------------------------------------------------- |
| `count` | integer | Requests counted today (UTC), including this one. Returns `0` if no row exists for today yet. |

#### Example JSON Response

```json
{
  "data": { "count": 12930 },
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Error Responses

| Status | When         | Body                                |
| ------ | ------------ | ----------------------------------- |
| `403`  | Not an admin | message: `"Admin access required."` (the request is still counted) |

---

### GET `/api/reports/workout-backups-count/`

Admin only. Returns the number of **distinct users** (any role) who have at least one
`WorkoutSession` row on the server. These rows are created by
[`POST /api/backup/workouts/upload/`](#11-backup--sync).

- This counts users, not sessions.
- The query uses `WorkoutSession.objects`, so soft-deleted rows are **not** excluded.
  In practice the workout sync hard-deletes and replaces a user's rows, so soft-deleted
  rows shouldn't exist.
- A user whose last sync sent an empty history has no rows, so they aren't counted.

**Permission:** `IsAdmin`

#### Response

| Field   | Type    | Description                                            |
| ------- | ------- | ------------------------------------------------------ |
| `count` | integer | Distinct `user` values in `backup_workout_sessions`    |

#### Example JSON Response

```json
{
  "data": { "count": 812 },
  "message": "",
  "status": 200,
  "time": "2026-06-30T11:30:00.123456"
}
```

#### Error Responses

| Status | When         | Body                                |
| ------ | ------------ | ----------------------------------- |
| `403`  | Not an admin | message: `"Admin access required."` |

---

## 11. Backup / Sync

All endpoints live under `/api/backup/` (`backup/urls.py`, mounted in `fit_&_fuel/urls.py`). There are **two separate sync models** in this app, and they behave very differently:

| Endpoints                                                                   | Data                       | Who                                   | Sync model                                                                                   |
| --------------------------------------------------------------------------- | -------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------- |
| `POST /api/backup/upload/`, `GET /api/backup/download/`                     | `attendance.Attendance`    | `admin`, `gym_owner`, `trainer`       | Per-record change log (create / update / delete), Last-Write-Wins on `updated_at`, soft delete |
| `POST /api/backup/workouts/upload/`, `GET /api/backup/workouts/download/`   | Workout sessions (nested)  | Any authenticated user, own data only | Whole-history replace (delete all of the caller's rows, re-insert payload)                   |
| `POST /api/backup/body-measurements/upload/`, `GET /api/backup/body-measurements/download/` | Body measurements | Any authenticated user, own data only | Whole-history replace                                                                        |

**Common behaviour (all six endpoints):**

- **Auth:** JWT bearer (`Authorization: Bearer <access_token>`). Missing/invalid token → `401`.
- **Body format:** JSON only (`Content-Type: application/json`). The global parser list also accepts form/multipart, but every upload view requires a top-level JSON **array** (`changes` / `sessions` / `measurements`); sent as form data it arrives as a string and fails the "must be a list" check. No endpoint in this app accepts files.
- **Size limits:** no request-size limit is configured in `settings.py` (`DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` are not set). DRF reads JSON bodies from the stream directly, so Django's 2.5 MB default is not expected to apply. Any limit in production comes from the web server / reverse proxy, which is not configured in this repo.
- **Storage:** all backup data is stored as rows in MySQL (`STRICT_TRANS_TABLES` sql_mode). Nothing is written to `MEDIA_ROOT`, and no backup files or snapshots are kept. Tables: `attendance`, `backup_workout_sessions`, `backup_session_exercises`, `backup_exercise_sets`, `backup_session_rest_breaks`, `backup_body_measurements`.
- **Versioning:** none. There is no version number, ETag, device id, or sync cursor. Only one server copy exists per user, and each workout/measurement upload overwrites it.
- **Timestamps:** `USE_TZ = True`, `TIME_ZONE = "UTC"`. Naive datetimes are interpreted as UTC (Django logs a `RuntimeWarning`).
- **Envelope:** every response is wrapped by `core.renderers.ResponseRenderer`:

  ```json
  {
    "data": { ... },
    "message": "",
    "status": 200,
    "time": "2026-09-23T10:15:30.123"
  }
  ```

  `time` is the server's local wall-clock time, **without a timezone offset** (`datetime.datetime.now()`). On non-2xx responses, `data` is `null` and `message` carries the `detail` string.

**Common errors:**

| Status | When                                   | `message`                                                                                                   |
| ------ | -------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `401`  | No `Authorization` header              | `"Authentication credentials were not provided."`                                                           |
| `401`  | Expired / malformed token              | `"Given token not valid for any token type"` (simplejwt)                                                    |
| `403`  | Role not allowed (attendance endpoints only) | Expected to be DRF's generic `"You do not have permission to perform this action."`. The `IsAdmin \| IsGymOwner \| IsTrainer` composition does not appear to surface the individual role messages (`"Admin access required."` etc.). Not verified at runtime. |

---

### POST `/api/backup/upload/`

Pushes a batch of client-side changes to the server as a list of change objects. Currently the **only syncable model is `attendance.Attendance`** (`_SYNCABLE` in `backup/views.py`). Any other `model` label is rejected per item.

**Permission:** `IsAdmin` | `IsGymOwner` | `IsTrainer` (members get `403`)

> **No scoping.** The view doesn't check that a record belongs to the caller's gym, or to the caller at all. Any admin, gym owner or trainer can create, overwrite or soft-delete **any** attendance row by UUID.

#### Sync semantics

Each change is processed on its own, in order. There is **no transaction**: earlier changes stay committed even if later ones fail.

| `action`               | `data.uuid`                          | Behaviour                                                                                                                                                                                                                                                                         |
| ---------------------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `create` **or** `update` (identical, upsert) | present, row exists (including soft-deleted rows) | **LWW check:** if `data.updated_at` is present, parses, and is `<=` the server row's `updated_at`, the change is **skipped** (`skipped += 1`). Otherwise every key in `data` except `uuid`, `created_at`, `updated_at`, `created_by`, `updated_by` is `setattr`'d onto the row, `updated_by` = caller, and the row is saved (`updated += 1`). |
| `create` / `update`    | present, row doesn't exist           | Row is **created with the client-supplied UUID** (`created += 1`). `created_at`/`updated_at` from the payload are discarded. `created_by` defaults to the caller unless the payload has it. `updated_by` = caller.                                                                    |
| `create` / `update`    | absent                               | Row is created with a **server-generated UUID** (`created += 1`). **The new UUID is not returned**, so the client can't reference that row later. Clients should always generate the UUID themselves.                                                                              |
| `delete`               | present, row exists                  | **Soft delete** (`is_deleted = true`, `deleted_at = now`, `updated_by` = caller) → `deleted += 1`. Deleting an already-deleted row soft-deletes it again and still counts as `deleted`.                                                                                        |
| `delete`               | present, row doesn't exist           | `skipped += 1`                                                                                                                                                                                                                                                                    |
| `delete`               | absent                               | **Silently ignored.** Not counted anywhere.                                                                                                                                                                                                                                         |
| anything else          | —                                    | Error item `{"action": ..., "error": "Unknown action."}`                                                                                                                                                                                                                          |

**LWW caveats:**

- The comparison is the **client's** `updated_at` against the server row's `updated_at`. The server value is `auto_now`, so it's the **server clock at the last save**, not the client's original edit time. Every save through this endpoint (or any other) resets it to server "now", so the client's timestamp does not survive.
- If `data.updated_at` is missing or can't be parsed (`parse_datetime` → `None`), there is **no conflict check** and the change always overwrites.
- A **naive** `updated_at` (no `Z`/offset) makes the aware/naive comparison throw, and the item lands in `errors` as `"can't compare offset-naive and offset-aware datetimes"`. Always send an offset.
- Update doesn't clear `is_deleted`. To revive a soft-deleted row, send `"is_deleted": false` (and `"deleted_at": null`) in `data`; any model field can be set this way.
- On **update**, unknown keys in `data` are silently accepted (set as plain Python attributes, never saved). On **create**, unknown keys raise and become an error item (`"Attendance() got unexpected keyword arguments: '<key>'"`).

#### Request

| Field              | Type   | Required | Description                                                                                          |
| ------------------ | ------ | -------- | ---------------------------------------------------------------------------------------------------- |
| `user_id`          | UUID   | No       | **Ignored.** The view never reads it.                                                                |
| `changes`          | array  | No       | List of change objects. Defaults to `[]` (a no-op that returns all-zero stats). Must be a JSON array. |
| `changes[].model`  | string | Yes      | Must be exactly `"attendance.Attendance"`                                                            |
| `changes[].action` | string | Yes      | `create` \| `update` \| `delete`                                                                     |
| `changes[].data`   | object | No       | Record payload. `null`/missing is treated as `{}`.                                                   |

Every element of `changes` must be a JSON object. A non-object element (e.g. a string) raises outside the per-item `try` and returns a `500`.

**`data` fields for `attendance.Attendance`:** values are assigned straight to model fields, with **no serializer validation**. Only DB/model-level checks apply.

| Field           | Type             | Required (create)  | Description                                                                                                                                                                                           |
| --------------- | ---------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uuid`          | UUID string      | Recommended        | Upsert key. Required for `delete`. An invalid UUID string becomes an error item (`"['“<value>” is not a valid UUID.']"`).                                                                            |
| `user_id`       | UUID string      | Yes                | The member/trainer the visit belongs to. **Send `user_id`, not `user`**: `Attendance.user` is a ForeignKey, and assigning a raw UUID string to it raises `ValueError` (reported as an error item). `limit_choices_to` (member/trainer only) is **not** enforced here. |
| `check_in`      | datetime string  | Yes                | ISO-8601 with offset, e.g. `2026-06-30T06:00:00Z`                                                                                                                                                     |
| `check_out`     | datetime \| null | No                 |                                                                                                                                                                                                       |
| `check_in_lat`  | decimal          | Yes                | `max_digits=9, decimal_places=6`. Not nullable.                                                                                                                                                       |
| `check_in_lng`  | decimal          | Yes                | `max_digits=9, decimal_places=6`. Not nullable.                                                                                                                                                       |
| `check_out_lat` | decimal \| null  | No                 | `max_digits=9, decimal_places=6`                                                                                                                                                                      |
| `check_out_lng` | decimal \| null  | No                 | `max_digits=9, decimal_places=6`                                                                                                                                                                      |
| `check_in_photo`  | string \| null | No                 | Stored verbatim as the file path in `ImageField`. No upload happens here; the file must already exist in storage.                                                                                     |
| `check_out_photo` | string \| null | No                 | Same as above                                                                                                                                                                                         |
| `updated_at`    | datetime string  | No (but needed for LWW) | Client's last-modified time. Used **only** for the LWW comparison, never stored.                                                                                                                  |
| `is_deleted` / `deleted_at` | bool / datetime | No        | Not intended as input, but accepted (see LWW caveats above)                                                                                                                                           |

#### Response

`200 OK` whenever `changes` is a list, even when every item failed.

| Field     | Type    | Description                                                                             |
| --------- | ------- | --------------------------------------------------------------------------------------- |
| `created` | integer | Rows created                                                                            |
| `updated` | integer | Rows updated                                                                            |
| `deleted` | integer | Rows soft-deleted                                                                       |
| `skipped` | integer | LWW skips (server not older than the client) + deletes of non-existent UUIDs            |
| `errors`  | array   | Per-item errors. **Shape varies**, see below                                            |

| Cause                                                   | `errors[]` item                                                                                  |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `model` isn't `"attendance.Attendance"` (checked first) | `{"model": "<model or null>", "error": "Unknown or unsupported model."}`                         |
| Known model, `action` not `create`/`update`/`delete`    | `{"action": "<action or null>", "error": "Unknown action."}`                                      |
| Any exception during create/update/delete               | `{"model": "<model>", "action": "<action>", "error": "<str(exception)>"}` (e.g. MySQL `(1048, "Column 'check_in' cannot be null")`) |

#### Example JSON Request

```json
{
  "changes": [
    {
      "model": "attendance.Attendance",
      "action": "create",
      "data": {
        "uuid": "e5f6a7b8-c9d0-4234-8f01-345678901234",
        "user_id": "b2c3d4e5-f6a7-4901-bcde-f12345678901",
        "check_in": "2026-06-30T06:00:00Z",
        "check_out": "2026-06-30T07:30:00Z",
        "check_in_lat": "19.075984",
        "check_in_lng": "72.877656",
        "check_out_lat": null,
        "check_out_lng": null,
        "updated_at": "2026-06-30T07:30:00Z"
      }
    },
    {
      "model": "attendance.Attendance",
      "action": "delete",
      "data": { "uuid": "0a1b2c3d-4e5f-4789-9abc-def012345678" }
    }
  ]
}
```

#### Example JSON Response

```json
{
  "data": {
    "created": 1,
    "updated": 0,
    "deleted": 1,
    "skipped": 0,
    "errors": []
  },
  "message": "",
  "status": 200,
  "time": "2026-06-30T07:31:02.415"
}
```

#### Error Responses

| Status | Condition                               | Body                                                                            |
| ------ | --------------------------------------- | ------------------------------------------------------------------------------- |
| `400`  | `changes` present but not a JSON array  | `{"data": null, "message": "changes must be a list.", "status": 400, "time": "..."}` |
| `403`  | Caller is a `member`                    | See *Common errors*                                                             |
| `500`  | An element of `changes` isn't an object | Unhandled `AttributeError`                                                      |

---

### GET `/api/backup/download/`

Returns **active** (not soft-deleted) attendance rows, optionally filtered by user and by server `updated_at`.

**Permission:** `IsAdmin` | `IsGymOwner` | `IsTrainer`

> **No scoping.** Without `user_id`, this returns attendance for **every user in every gym**. With `user_id`, it returns that user's rows whatever gym they belong to.

> **Deletions aren't propagated.** The queryset is `Attendance.active_objects` (`is_deleted=False`), so soft-deleted rows are simply missing from the response. No tombstones are sent, and the serializer doesn't include `is_deleted`/`updated_at`. An incremental (`since`) pull can't tell a client that a record was deleted.

#### Query parameters

| Param       | Type            | Required | Description                                                                                                                                                                                                                                                                                                   |
| ----------- | --------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `user_id`   | UUID            | No       | Filter to rows where `user.uuid == user_id`. A malformed UUID raises a Django `ValidationError`, which DRF doesn't handle → `500`.                                                                                                                                                                           |
| `since`     | ISO-8601 datetime | No     | Returns rows with **`updated_at >= since`** (inclusive), compared against the server-side `updated_at`. Parsed with Django `parse_datetime`. If the format isn't recognised, the filter is **silently dropped** and all rows are returned. **URL-encode `+`** in offsets (`%2B00:00`) or use `Z`: a raw `+` decodes to a space, parsing fails, and you get the full set. A naive value is treated as UTC. |
| `page_size` | integer         | No       | Enables pagination (`core.pagination.OptionalPagination`). Omitted, `0`, negative or non-numeric → **no pagination** (all rows). Capped at `100`.                                                                                                                                                              |
| `page`      | integer         | No       | 1-based page number, used only when `page_size > 0`. Out of range → `404` `"Invalid page."`                                                                                                                                                                                                                     |

Ordering: `Attendance.Meta.ordering = ["-check_in"]` (newest check-in first).

#### Response

| Field                | Type            | Description                                                                                                                                                             |
| -------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `changes.attendance` | array \| object | Without pagination: array of attendance objects. With `page_size > 0`: a nested envelope `{"count", "next", "previous", "results"}` at this key. The top-level envelope is **not** unwrapped, because the pagination keys are nested under `changes`. |

**Attendance object** (`AttendanceSerializer`):

| Field             | Type             | Description                                                                                            |
| ----------------- | ---------------- | ------------------------------------------------------------------------------------------------------ |
| `uuid`            | UUID             | Record id                                                                                              |
| `user`            | UUID             | Member/trainer UUID                                                                                    |
| `user_name`       | string           | `user.get_full_name()`                                                                                 |
| `user_type`       | string           | `member` \| `trainer` (whatever the user's `user_type` is)                                             |
| `check_in`        | datetime         | UTC, `Z` suffix                                                                                        |
| `check_out`       | datetime \| null |                                                                                                        |
| `check_in_lat`    | decimal string   | e.g. `"19.075984"`                                                                                     |
| `check_in_lng`    | decimal string   |                                                                                                        |
| `check_out_lat`   | decimal string \| null |                                                                                                  |
| `check_out_lng`   | decimal string \| null |                                                                                                  |
| `check_in_photo`  | string \| null   | Media URL. The serializer gets no request context here, so it's likely a **relative** path (e.g. `/media/attendance_photos/x.jpg`), not an absolute URL. |
| `check_out_photo` | string \| null   | Same as above                                                                                          |

`updated_at`, `created_at` and `is_deleted` are **not** returned. To run incremental sync, the client should record the envelope's request time (or its own clock) as the next `since`. Keep in mind that the envelope `time` has no offset and is in server local time.

#### Example JSON Response (unpaginated)

```json
{
  "data": {
    "changes": {
      "attendance": [
        {
          "uuid": "e5f6a7b8-c9d0-4234-8f01-345678901234",
          "user": "b2c3d4e5-f6a7-4901-bcde-f12345678901",
          "user_name": "Rahul Patil",
          "user_type": "member",
          "check_in": "2026-06-30T06:00:00Z",
          "check_out": "2026-06-30T07:30:00Z",
          "check_in_lat": "19.075984",
          "check_in_lng": "72.877656",
          "check_out_lat": null,
          "check_out_lng": null,
          "check_in_photo": null,
          "check_out_photo": null
        }
      ]
    }
  },
  "message": "",
  "status": 200,
  "time": "2026-06-30T08:00:00.000"
}
```

#### Example JSON Response (`?page_size=1&page=1`)

```json
{
  "data": {
    "changes": {
      "attendance": {
        "count": 2,
        "next": "http://<host>/api/backup/download/?page=2&page_size=1",
        "previous": null,
        "results": [ { "uuid": "e5f6a7b8-c9d0-4234-8f01-345678901234", "...": "..." } ]
      }
    }
  },
  "message": "",
  "status": 200,
  "time": "2026-06-30T08:00:00.000"
}
```

#### Error Responses

| Status | Condition                  | `message`                                  |
| ------ | -------------------------- | ------------------------------------------ |
| `403`  | Caller is a `member`       | See *Common errors*                        |
| `404`  | `page` out of range        | `"Invalid page."`                          |
| `500`  | `user_id` isn't a valid UUID | Unhandled Django `ValidationError`       |

---

### POST `/api/backup/workouts/upload/`

Replaces the caller's **entire** server-side workout history with the request body. This mirrors the local app's `workout_sessions` / `session_exercises` / `exercise_sets` / `session_rest_breaks` tables.

**Permission:** `IsAuthenticatedUser` (any role; always acts on `request.user`)

#### Sync semantics

- Inside one `transaction.atomic()`, the server **hard-deletes** every `WorkoutSession` owned by the caller (cascading to exercises, sets and rest breaks), then inserts every session in the payload.
- If anything raises, the whole transaction rolls back, the previous server copy stays intact, and you get a `400` with the exception text.
- There are **no upsert keys, no conflict resolution, no timestamps and no tombstones**. The payload *is* the new state. Server UUIDs are regenerated on every sync and never exposed.
- ⚠️ **An empty `sessions` array, or a body with no `sessions` key at all, wipes the user's entire server history** and returns `synced_sessions: 0`. Clients should never send a partial or empty history unless they mean to erase it.
- Other users' data is never touched (covered by `test_sync_does_not_affect_other_users`).
- **No serializer validation:** values go straight to `Model.objects.create()`. Type and constraint errors come from Django field conversion or MySQL (strict mode) and surface as `400` with the raw error string.
- Booleans are coerced with Python `bool()`, so any non-empty string (including `"false"`) becomes `true`. Send real JSON booleans.

#### Request

| Field                         | Type            | Required | Validation / default                                                                                          |
| ----------------------------- | --------------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| `sessions`                    | array           | No*      | Must be a JSON array. Defaults to `[]` if missing, *which deletes everything*.                                |
| `sessions[].session_date`     | string          | **Yes**  | `YYYY-MM-DD` only. A datetime string is rejected. Missing/null → MySQL NOT NULL error.                        |
| `sessions[].duration_minutes` | integer         | No       | `null`/`0`/missing → `0`. Unsigned; negative → MySQL out-of-range error.                                      |
| `sessions[].notes`            | string \| null  | No       | Unlimited text                                                                                                |
| `sessions[].calories_burned`  | number \| null  | No       | Float                                                                                                         |
| `sessions[].is_rest_day`      | boolean         | No       | Default `false`                                                                                               |
| `sessions[].exercises`        | array           | No       | Default `[]`. An explicit `null` fails (`'NoneType' object is not iterable`).                                 |
| `sessions[].rest_breaks`      | array           | No       | Default `[]`. An explicit `null` fails the same way.                                                          |

**`exercises[]` object** (`SessionExercise`):

| Field            | Type            | Required | Validation / default                                                        |
| ---------------- | --------------- | -------- | --------------------------------------------------------------------------- |
| `exercise_name`  | string          | No       | Default `""` (empty allowed). Max 255 chars; longer → MySQL "Data too long" error. |
| `body_part`      | string \| null  | No       | Max 100 chars                                                               |
| `muscle`         | string \| null  | No       | Max 100 chars                                                               |
| `is_unilateral`  | boolean         | No       | Default `false`                                                             |
| `set_type`       | string          | No       | `null`/empty → `"normal"`. Free text, max 20 chars, no enum enforced.       |
| `superset_group` | integer \| null | No       | Signed integer                                                              |
| `sets`           | array           | No       | Default `[]`. An explicit `null` fails.                                     |

**`sets[]` object** (`ExerciseSet`):

| Field              | Type            | Required | Validation / default                                                              |
| ------------------ | --------------- | -------- | --------------------------------------------------------------------------------- |
| `set_number`       | integer         | No       | `null`/`0`/missing → **1-based position** in the `sets` array. Unsigned.          |
| `reps`             | integer \| null | No       | Unsigned                                                                          |
| `weight_kg`        | number \| null  | No       | Float                                                                             |
| `duration_seconds` | integer \| null | No       | Unsigned                                                                          |
| `speed_kmh`        | number \| null  | No       | Float                                                                             |

**`rest_breaks[]` object** (`SessionRestBreak`):

| Field              | Type    | Required | Validation / default                                                                                          |
| ------------------ | ------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| `duration_minutes` | integer | No       | `null`/`0`/missing → `0`. Unsigned.                                                                           |
| `sort_index`       | integer | No       | Missing → **0-based position** in the array. An explicit `null` is *not* defaulted and fails with a NOT NULL error. Unsigned. |

#### Response

| Field             | Type    | Description                                                              |
| ----------------- | ------- | ------------------------------------------------------------------------ |
| `synced_sessions` | integer | Number of sessions now stored for the caller (after the replace)         |

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
          "superset_group": null,
          "sets": [
            { "set_number": 1, "reps": 10, "weight_kg": 60.0, "duration_seconds": null, "speed_kmh": null },
            { "set_number": 2, "reps": 8, "weight_kg": 65.0, "duration_seconds": null, "speed_kmh": null }
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
  "data": { "synced_sessions": 1 },
  "message": "",
  "status": 200,
  "time": "2026-01-15T09:30:00.512"
}
```

#### Error Responses

All `400`s have `data: null` and put the text in `message`. Because of the rollback, no data changes on a `400`.

| Status | Condition                                   | `message` (examples)                                                                                          |
| ------ | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `400`  | `sessions` isn't an array                   | `"sessions must be a list."`                                                                                  |
| `400`  | Missing/null `session_date`                 | `(1048, "Column 'session_date' cannot be null")`                                                              |
| `400`  | Badly formatted `session_date`              | `['“2026-01-15T10:00:00Z” value has an invalid date format. It must be in YYYY-MM-DD format.']`               |
| `400`  | Non-numeric number field                    | e.g. `Field 'weight_kg' expected a number but got 'abc'.`                                                     |
| `400`  | Nested array sent as `null`, or a non-object element | e.g. `'NoneType' object is not iterable` / `'str' object has no attribute 'get'`                      |
| `400`  | Negative unsigned value / string too long   | Raw MySQL error text (e.g. `(1264, "Out of range value for column ...")`, `(1406, "Data too long for column ...")`) |

---

### GET `/api/backup/workouts/download/`

Returns the caller's **entire** server-side workout history, nested in the same shape the upload accepts. There's no `since` filter and no pagination.

**Permission:** `IsAuthenticatedUser` (any role; own data only)

**Query parameters:** none.

#### Response

| Field                         | Type            | Description                                                                        |
| ----------------------------- | --------------- | ---------------------------------------------------------------------------------- |
| `sessions`                    | array           | All of the caller's sessions, ordered by `session_date` **ascending**. Order among sessions with the same date is not defined. |
| `sessions[].session_date`     | string          | `YYYY-MM-DD`                                                                       |
| `sessions[].duration_minutes` | integer         |                                                                                    |
| `sessions[].notes`            | string \| null  |                                                                                    |
| `sessions[].calories_burned`  | number \| null  |                                                                                    |
| `sessions[].is_rest_day`      | boolean         |                                                                                    |
| `sessions[].exercises[]`      | array           | `exercise_name`, `body_part`, `muscle`, `is_unilateral`, `set_type`, `superset_group`, `sets[]`. **No explicit ordering** (DB order, likely but not guaranteed to be insertion order). |
| `exercises[].sets[]`          | array           | `set_number`, `reps`, `weight_kg`, `duration_seconds`, `speed_kmh`. No explicit ordering, so sort by `set_number` client-side. |
| `sessions[].rest_breaks[]`    | array           | `duration_minutes`, `sort_index`. No explicit ordering, so sort by `sort_index` client-side. |

Every key is always present (nulls included). Server UUIDs and timestamps are not returned.

#### Example JSON Response

```json
{
  "data": {
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
            "superset_group": null,
            "sets": [
              { "set_number": 1, "reps": 10, "weight_kg": 60.0, "duration_seconds": null, "speed_kmh": null },
              { "set_number": 2, "reps": 8, "weight_kg": 65.0, "duration_seconds": null, "speed_kmh": null }
            ]
          }
        ],
        "rest_breaks": [{ "duration_minutes": 2, "sort_index": 0 }]
      }
    ]
  },
  "message": "",
  "status": 200,
  "time": "2026-01-16T07:00:00.000"
}
```

#### Error Responses

Only the auth errors from *Common errors* (`401`).

---

### POST `/api/backup/body-measurements/upload/`

Replaces the caller's **entire** server-side body-measurement history (mirrors the local app's `user_profiles` table). The semantics are the same as `/api/backup/workouts/upload/`: one atomic transaction that hard-deletes all of the caller's `BodyMeasurement` rows and then re-inserts the payload. On any error it rolls back and returns `400`.

**Permission:** `IsAuthenticatedUser` (any role; own data only)

⚠️ An empty or missing `measurements` array **deletes all** of the caller's server-side measurements. No upsert keys, no timestamps-based merge, no tombstones, no versioning.

#### Request

| Field                             | Type            | Required | Validation / default                                                                                                                                  |
| --------------------------------- | --------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `measurements`                    | array           | No*      | Must be a JSON array. Defaults to `[]`, which *wipes history*.                                                                                        |
| `measurements[].age`              | integer \| null | No       | Unsigned                                                                                                                                              |
| `measurements[].gender`           | string \| null  | No       | Free text, max 20 chars, no enum enforced                                                                                                             |
| `measurements[].is_correction`    | boolean         | No       | Default `false` (coerced with `bool()`)                                                                                                               |
| `measurements[].weight_kg`        | number \| null  | No       | Float                                                                                                                                                 |
| `measurements[].height_cm`        | number \| null  | No       | Float                                                                                                                                                 |
| `measurements[].chest_cm`         | number \| null  | No       | Float                                                                                                                                                 |
| `measurements[].waist_cm`         | number \| null  | No       | Float                                                                                                                                                 |
| `measurements[].biceps_cm`        | number \| null  | No       | Float                                                                                                                                                 |
| `measurements[].thighs_cm`        | number \| null  | No       | Float                                                                                                                                                 |
| `measurements[].neck_cm`          | number \| null  | No       | Float                                                                                                                                                 |
| `measurements[].hip_cm`           | number \| null  | No       | Float                                                                                                                                                 |
| `measurements[].body_fat_percent` | number \| null  | No       | Float. No range check.                                                                                                                                |
| `measurements[].recorded_at`      | datetime string | **Yes**  | ISO-8601, e.g. `2026-01-15T08:30:00Z`. Send an offset: a naive value is stored as UTC. A date-only string is accepted as midnight. Missing/null → NOT NULL error. |

#### Response

| Field                 | Type    | Description                                                         |
| --------------------- | ------- | ------------------------------------------------------------------- |
| `synced_measurements` | integer | Number of measurement rows now stored for the caller (after the replace) |

#### Example JSON Request

```json
{
  "measurements": [
    {
      "age": 28,
      "gender": "male",
      "is_correction": false,
      "weight_kg": 72.5,
      "height_cm": 178.0,
      "chest_cm": 100.0,
      "waist_cm": 82.0,
      "biceps_cm": 35.0,
      "thighs_cm": 55.0,
      "neck_cm": 38.0,
      "hip_cm": 95.0,
      "body_fat_percent": 15.5,
      "recorded_at": "2026-01-15T08:30:00Z"
    }
  ]
}
```

#### Example JSON Response

```json
{
  "data": { "synced_measurements": 1 },
  "message": "",
  "status": 200,
  "time": "2026-01-15T08:31:00.204"
}
```

#### Error Responses

| Status | Condition                              | `message` (examples)                                                                                                   |
| ------ | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `400`  | `measurements` isn't an array          | `"measurements must be a list."`                                                                                       |
| `400`  | Missing/null `recorded_at`             | `(1048, "Column 'recorded_at' cannot be null")`                                                                        |
| `400`  | Badly formatted `recorded_at`          | `['“<value>” value has an invalid format. It must be in YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format.']`                  |
| `400`  | Non-numeric number / negative `age` / `gender` > 20 chars / non-object element | Raw Django/MySQL error text                                                    |

---

### GET `/api/backup/body-measurements/download/`

Returns the caller's **entire** server-side body-measurement history, ordered by `recorded_at` **descending** (newest first). There's no `since` filter and no pagination.

**Permission:** `IsAuthenticatedUser` (any role; own data only)

**Query parameters:** none.

#### Response

| Field          | Type  | Description                                                                                                                                         |
| -------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `measurements` | array | Same fields as the upload request, all always present. `recorded_at` comes from Python `isoformat()`, so it has a **`+00:00`** offset (not `Z`) and includes microseconds only when they're non-zero. |

#### Example JSON Response

```json
{
  "data": {
    "measurements": [
      {
        "age": 28,
        "gender": "male",
        "is_correction": false,
        "weight_kg": 72.5,
        "height_cm": 178.0,
        "chest_cm": 100.0,
        "waist_cm": 82.0,
        "biceps_cm": 35.0,
        "thighs_cm": 55.0,
        "neck_cm": 38.0,
        "hip_cm": 95.0,
        "body_fat_percent": 15.5,
        "recorded_at": "2026-01-15T08:30:00+00:00"
      }
    ]
  },
  "message": "",
  "status": 200,
  "time": "2026-01-16T07:00:00.000"
}
```

#### Error Responses

Only the auth errors from *Common errors* (`401`).

---

## 12. Utility

### HEAD `/api/health/`

Liveness probe. Plain Django function view (`@require_http_methods(["HEAD"])`), not a DRF view — no auth, no envelope, not in the OpenAPI schema.

**Permission:** Public (no authentication performed)

#### Request

No parameters, no body.

#### Response

`200 OK`, empty body.

#### Error Responses

| Status | When |
| --- | --- |
| `405 Method Not Allowed` | Any method other than `HEAD` — **including `GET`**. Django's `HttpResponseNotAllowed` (empty body, `Allow: HEAD` header, no envelope) |

Note: each call is counted by `RequestCounterMiddleware`.

---

### GET `/api/my-ip/`

Returns IP geolocation plus parsed User-Agent information for the caller (or for an explicit IP).

**Permission:** Public (`authentication_classes = []`, `permission_classes = []`; any token sent is ignored)

**Envelope:** **None** — this view uses DRF's plain `JSONRenderer` (`core.renderers.JSONRenderer` is just the re-exported DRF class), so the object below is returned at the top level, and errors are `{"detail": "…"}`.

#### Request

Query parameters:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ip` | string | No | IPv4/IPv6 address to look up. If present (even empty), it is used instead of the client IP and must be a globally routable address (`ipaddress.ip_address(ip).is_global`). If absent, the client IP is resolved with `django-ipware` `get_client_ip(request)` (honours `X-Forwarded-For` etc.) |

Headers: `User-Agent` (optional) is parsed with `user-agents`.

Location lookup uses Django's `GeoIP2` with the MaxMind database at `GEOIP_PATH = "static/geo_lite2/GeoLite2-City.mmdb"` (relative to the process working directory; the file is not in the repo).

#### Response

`200 OK`

| Field | Type | Description |
| --- | --- | --- |
| `ip` | string | The IP that was looked up |
| `location` | object | From `GeoIP2.city(ip)` |
| `location.country` | string \| null | `country_name` |
| `location.city` | string \| null | `city` |
| `location.region` | string \| null | GeoIP2's `region` key — in Django's `GeoIP2` this is the subdivision **code** (e.g. `"MH"`), not the full name (not verified at runtime) |
| `location.latitude` | number \| null | Latitude |
| `location.longitude` | number \| null | Longitude |
| `browser` | object | |
| `browser.name` | string | Browser family (e.g. `"Chrome"`, `"Other"` if unknown) |
| `browser.version` | string | Version string (may be `""`) |
| `os` | object | |
| `os.name` | string | OS family (e.g. `"Android"`, `"Other"`) |
| `os.version` | string | Version string (may be `""`) |
| `device` | object | |
| `device.type` | string | `mobile` \| `tablet` \| `pc` \| `unknown` (checked in that order) |
| `device.brand` | string \| null | Device brand |
| `device.model` | string \| null | Device model |
| `is_bot` | boolean | Whether the UA looks like a bot |

#### Example JSON Response

```json
{
  "ip": "103.21.244.0",
  "location": {
    "country": "India",
    "city": "Mumbai",
    "region": "MH",
    "latitude": 19.076,
    "longitude": 72.8777
  },
  "browser": { "name": "Chrome Mobile", "version": "125.0.0" },
  "os": { "name": "Android", "version": "14" },
  "device": { "type": "mobile", "brand": "Samsung", "model": "SM-S921B" },
  "is_bot": false
}
```

#### Error Responses

All unwrapped (no envelope).

| Status | Body | When |
| --- | --- | --- |
| `400 Bad Request` | `{"detail": "IP <ip> is private or not routable."}` | IP is private/loopback/reserved, or no client IP could be determined (renders as `"IP None is private or not routable."`) |
| `404 Not Found` | `{"ip": "<ip>", "detail": "Location not found"}` | `GeoIP2.city(ip)` raised (address not in the database) |
| `400 Bad Request` | `{"detail": "Unable to get IP location: <exception text>"}` | Any other exception — e.g. malformed `?ip=` (`"'abc' does not appear to be an IPv4 or IPv6 address"`), or the GeoIP database file missing/unloadable |

---

### POST `/api/upload-file/`

Uploads an image and returns its absolute URL. This is step one for every image field in the API (`profile_picture`, `gym_picture`, attendance `photo`, music `thumb`/`icon`/`cover`): upload here, then send the returned `url` string in the JSON/form body of the real create/update request (see [Media files & uploads](#media-files--uploads)).

**Permission:** Any authenticated user (global `IsAuthenticated`)

**Content-Type:** `multipart/form-data`

#### Request

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | file | Yes | Image file. Validated in this order: (1) DRF `ImageField` — must be a real file that Pillow can open; (2) extension (from the filename, case-insensitive) in `jpeg`, `jpg`, `png`, `webp`; (3) size ≤ 5 MB (`5 * 1024 * 1024` bytes) |

Storage: saved via `default_storage` as `uploads/<uuid4 hex>.<ext>` under `MEDIA_ROOT` (i.e. `<BASE_DIR>/media/uploads/…`). The original filename is discarded; the extension is lower-cased. The file is not linked to any record until another request references its URL — uploaded files are never cleaned up.

#### Response

`201 Created`

| Field | Type | Description |
| --- | --- | --- |
| `url` | string | Absolute URL built with `request.build_absolute_uri(default_storage.url(path))`, e.g. `http://<host>/media/uploads/<hex>.<ext>` |

#### Example JSON Response

```json
{
  "data": {
    "url": "http://<host>/media/uploads/1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b.jpg"
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:15:30.123456"
}
```

#### Error Responses

Validation errors are field dicts, so `data` and `message` are both `{"file": ["…"]}`.

| Status | Message | When |
| --- | --- | --- |
| `400` | `{"file": ["No file was submitted."]}` | `file` key missing from a multipart body |
| `400` | `{"file": ["The submitted data was not a file. Check the encoding type on the form."]}` | `file` sent as a non-file value (e.g. a JSON/form string) |
| `400` | `{"file": ["The submitted file is empty."]}` | Zero-byte file |
| `400` | `{"file": ["Upload a valid image. The file you uploaded was either not an image or a corrupted image."]}` | Pillow cannot open the file |
| `400` | `{"file": ["Unsupported file type. Allowed: jpeg, jpg, png, webp."]}` | Extension not in the allowed set (or no extension) |
| `400` | `{"file": ["File too large — max 5MB."]}` | Size > 5,242,880 bytes |
| `401` | `"Authentication credentials were not provided."` / `"Given token not valid for any token type"` | Missing / invalid access token |

(The first four messages are DRF's built-in `FileField`/`ImageField` texts, quoted from DRF defaults rather than from this repo.)

---

## 13. Music (Playlists & Songs)

Admin-managed music catalogue served to the Flutter app (`music` app, mounted at
`/api/music/`). Both resources are registered on a DRF `DefaultRouter`, so each
exposes list / create / retrieve / update / delete, plus the project-wide
`POST /{id}/update/` partial-update action inherited from `core.views.BaseModelViewSet`.
`PATCH` is **not** allowed (`http_method_names` = `get, post, put, delete, head, options`).

**Ids are integers, not UUIDs.** Unlike every other model in the project, `Song`
and `Playlist` use a `BigAutoField` integer primary key. The ids are a contract with
the Flutter app's bundled `songs.json` / `playlists.json`, so backend-created rows
must continue the seeded sequence. The seed data shipped in `music/seed_data/`
currently holds **165 songs (ids `1..165`)** and **9 playlists (ids `1..9`)**, so
admin-created rows start at `166` / `10` (see [`seed_music`](#seed_music-management-command)).

> Note: `music/models.py` (docstring: "`1..138` / `1..7`") and
> `music/seed_data/README.md` ("138-song", "7-playlist", "continue from id `139` / `8`")
> are stale. The actual seed JSON files and the `seed_music` help text (`166 / 10`)
> agree on 165 / 9.

### Bundled vs remote

Every song and playlist carries `is_remote`:

| `is_remote` | Stored in                                                   | Media fields in the response                                     |
| ----------- | ----------------------------------------------------------- | ----------------------------------------------------------------- |
| `false`     | `thumb_ref` / `asset_ref` / `icon_ref` / `cover_ref` (text) | The literal app-bundle path, e.g. `assets/audio-opus/foo.opus`    |
| `true`      | `thumb_file` / `asset_file` / `icon_file` / `cover_file`    | Absolute URL built with `request.build_absolute_uri()`, e.g. `http://<host>/media/music/audio/foo.opus` |

Resolution rule (`MediaRefMixin._resolve`): if the uploaded file field is set, return
its absolute URL; otherwise return the `*_ref` string; if that is empty/null, return
`null` (the app falls back to its default artwork).

With the default seed (`--remote-playlists 4,5,6,7,8,9`), playlists `1..3` are bundled
and `4..9` are remote; a song is remote only if **every** playlist that contains it is
remote. Anything created through the API is always `is_remote = true` (forced in
`SongCreateSerializer.create` / `PlaylistCreateSerializer.create`).

### Media upload model

- `thumb` (song), `icon` and `cover` (playlist) are **URL strings**, not files. Upload
  the image first via `POST /api/upload-file/` (see [Utility](#12-utility)) and send the
  returned `url`. The field (`core.serializers.UploadedFileURLField`) strips the URL to
  its path, requires it to start with `MEDIA_URL` (`/media/`), and requires the file
  to exist in storage. The stored file stays where `/api/upload-file/` put it
  (`media/uploads/<hex>.<ext>`), it is **not** moved into `music/thumbs/` etc.
- `asset` (song audio) is a **real file part** and must have a `.opus` filename.
  Song create/replace therefore needs `multipart/form-data`.
- Playlists have no file fields, so playlist writes accept either
  `application/json` or `multipart/form-data` (both parsers are enabled globally).

### Permissions (both resources)

| Action                                                | Permission class      | Failure                                                                 |
| ----------------------------------------------------- | --------------------- | ----------------------------------------------------------------------- |
| `list`, `retrieve`                                    | `IsAuthenticatedUser` | `401` `"Authentication credentials were not provided."` if no/invalid token |
| `create`, `update` (PUT), `partial_update_via_post`, `destroy` | `IsAdmin` (`user_type == admin`) | `401` if unauthenticated; `403` `"Admin access required."` for any other role |

Any admin may edit/delete a row created by another admin (there is no ownership check).

### Filtering, search, ordering, pagination

- No filter, search, or ordering parameters are supported (the global
  `DjangoFilterBackend` is active but no `filterset_fields` are defined). Results are
  always ordered by `id` ascending.
- Pagination is **opt-in** (`core.pagination.OptionalPagination`):

| Param       | Type    | Required | Description                                                                                          |
| ----------- | ------- | -------- | ---------------------------------------------------------------------------------------------------- |
| `page_size` | integer | No       | Omitted, `0`, negative, or non-integer returns **all rows unpaginated**. A positive value (capped at `100`) enables pagination. |
| `page`      | integer | No       | Page number; only meaningful when `page_size` is positive. An out-of-range page returns `404` `"Invalid page."` |

Unpaginated responses have `data` as a plain array and **no** `count`/`next`/`previous`
keys. Paginated responses add `count`, `next`, `previous`.

Soft-deleted rows (`is_deleted = true`) are excluded from list and retrieve
(`active_objects` manager); retrieving one returns `404`.

---

### GET `/api/music/songs/`

List all non-deleted songs.

**Permission:** `IsAuthenticatedUser`

**Query parameters:** `page_size`, `page` (see above).

#### Response (`data[]`)

| Field       | Type           | Description                                                                         |
| ----------- | -------------- | ----------------------------------------------------------------------------------- |
| `id`        | integer        | Song id                                                                             |
| `title`     | string         | Song title (max 255)                                                                |
| `artist`    | string         | Artist name; may be `""`                                                            |
| `thumb`     | string \| null | `assets/...` path (bundled), absolute URL (remote), or `null` if none               |
| `asset`     | string \| null | `assets/...opus` path (bundled), absolute URL (remote), or `null` if none           |
| `duration`  | integer        | Length in seconds (client-supplied; defaults to `0`, never computed from the audio) |
| `is_remote` | boolean        | `false` = bundled in the app, `true` = served from the server                       |

#### Example JSON Response (unpaginated)

```json
{
  "data": [
    {
      "id": 1,
      "title": "Sukhharta Dukhharta",
      "artist": "Amitabh Bachchan",
      "thumb": "assets/audio-thumb/sukhharta_dukhharta.png",
      "asset": "assets/audio-opus/sukhharta_dukhharta.opus",
      "duration": 122,
      "is_remote": false
    },
    {
      "id": 133,
      "title": "3:59 AM",
      "artist": "Divine",
      "thumb": "http://<host>/media/music/thumbs/<file>.png",
      "asset": "http://<host>/media/music/audio/<file>.opus",
      "duration": 286,
      "is_remote": true
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:00:00.123"
}
```

#### Example JSON Response (`?page_size=2&page=1`)

```json
{
  "data": [ { "id": 1, "...": "..." }, { "id": 2, "...": "..." } ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:00:00.123",
  "count": 165,
  "next": "http://<host>/api/music/songs/?page=2&page_size=2",
  "previous": null
}
```

---

### POST `/api/music/songs/`

Create a song. The `id` is auto-assigned; `is_remote` is forced to `true`; `created_by`
is set to the caller. The response uses the read shape (`SongSerializer`).

**Permission:** `IsAdmin` · **Content-Type:** `multipart/form-data` (required, because of `asset`)

#### Request

| Field      | Type    | Required | Description                                                                                                                  |
| ---------- | ------- | -------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `title`    | string  | Yes      | Max 255 chars                                                                                                                |
| `artist`   | string  | No       | Max 255 chars; blank allowed                                                                                                 |
| `duration` | integer | No       | Seconds, `>= 0`; defaults to `0` if omitted                                                                                  |
| `thumb`    | string  | Yes      | URL returned by `POST /api/upload-file/`. The field is `required=True` but also `allow_null=True`, so an explicit empty/null value is accepted and stores no thumbnail |
| `asset`    | file    | Yes      | Audio file whose filename ends in `.opus` (only the extension is checked, not the content)                                  |

Example (multipart form fields):

```
title=New Track
artist=New Artist
duration=210
thumb=http://<host>/media/uploads/3f9c1a2b4d5e6f708192a3b4c5d6e7f8.png
asset=@new_track.opus
```

#### Example JSON Response (`201 Created`)

```json
{
  "data": {
    "id": 166,
    "title": "New Track",
    "artist": "New Artist",
    "thumb": "http://<host>/media/uploads/3f9c1a2b4d5e6f708192a3b4c5d6e7f8.png",
    "asset": "http://<host>/media/music/audio/new_track.opus",
    "duration": 210,
    "is_remote": true
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:00:00.123"
}
```

#### Error Responses

Validation errors (`400`) put the DRF error dict in both `data` and `message`, e.g.
`{"data": {"asset": ["Audio must be a .opus file."]}, "message": {"asset": ["Audio must be a .opus file."]}, "status": 400, ...}`.

| Status             | When / literal message                                                                                     |
| ------------------ | ---------------------------------------------------------------------------------------------------------- |
| `400 Bad Request`  | Missing `title`/`thumb`/`asset`: `"This field is required."`                                               |
| `400 Bad Request`  | `asset` not `.opus`: `"Audio must be a .opus file."`                                                       |
| `400 Bad Request`  | `thumb` sent as a raw file: `"Expected the URL returned by POST /api/upload-file/, not a raw file."`       |
| `400 Bad Request`  | `thumb` URL path not under `/media/`: `"Must be a URL returned by POST /api/upload-file/."`                |
| `400 Bad Request`  | `thumb` points to a non-existent file: `"Uploaded file not found."`                                        |
| `400 Bad Request`  | Negative `duration`: `"Ensure this value is greater than or equal to 0."`                                  |
| `401 Unauthorized` | No/invalid token                                                                                           |
| `403 Forbidden`    | Caller is not an admin: `"Admin access required."`                                                         |

---

### GET `/api/music/songs/{id}/`

Retrieve one non-deleted song. **Permission:** `IsAuthenticatedUser`. `data` is a single
song object (same fields as the list). `404` (`"No Song matches the given query."`) if the
id doesn't exist or is soft-deleted.

---

### PUT `/api/music/songs/{id}/`

Full replace. **Permission:** `IsAdmin` · `multipart/form-data`. Same fields and
validation as `POST` — `title`, `thumb` and `asset` are all required again (a new
`.opus` file must be re-uploaded). Returns `200` with the read-shaped song. `is_remote`
is **not** changed on update (it stays whatever it was, including `false` for a
bundled song).

---

### POST `/api/music/songs/{id}/update/`

Partial update (project's POST-instead-of-PATCH convention). **Permission:** `IsAdmin` ·
`multipart/form-data` (JSON also parses, but then `asset` cannot be sent). Any subset of
`title`, `artist`, `duration`, `thumb`, `asset`; omitted fields are untouched. Returns
`200` with the read-shaped song.

> Caveat: if an admin sets `thumb`/`asset` on a bundled (`is_remote = false`) song, the
> uploaded file takes precedence in the response (file wins over `*_ref`) but
> `is_remote` stays `false`.

---

### DELETE `/api/music/songs/{id}/`

Soft delete: sets `is_deleted = true`, `deleted_at = now()`. The id is never reused.
**Permission:** `IsAdmin`. Returns `204 No Content`.

> Soft-deleting a song does **not** remove its `PlaylistSong` rows, so deleted song ids
> keep appearing in the `song_ids` of playlists that contained them.

---

### GET `/api/music/playlists/`

List all non-deleted playlists.

**Permission:** `IsAuthenticatedUser`

**Query parameters:** `page_size`, `page` (see above).

#### Response (`data[]`)

| Field       | Type             | Description                                                                           |
| ----------- | ---------------- | ------------------------------------------------------------------------------------- |
| `id`        | integer          | Playlist id                                                                           |
| `title`     | string           | Playlist title (max 255)                                                              |
| `icon`      | string \| null   | `assets/...` path (bundled), absolute URL (remote), or `null`                         |
| `cover`     | string \| null   | `assets/...` path (bundled), absolute URL (remote), or `null`                         |
| `color`     | string           | Hex without `#` (6 or 8 hex digits, e.g. `520102`); may be `""`                       |
| `song_ids`  | array of integer | Song ids in `position` order (may include soft-deleted song ids, see above)           |
| `is_remote` | boolean          | `false` = bundled, `true` = served from the server                                    |

#### Example JSON Response

```json
{
  "data": [
    {
      "id": 1,
      "title": "Devotional",
      "icon": "assets/playlist-thumb/devotional_icon.png",
      "cover": "assets/playlist-thumb/devotional.png",
      "color": "520102",
      "song_ids": [1, 2, 3, 4, 5],
      "is_remote": false
    },
    {
      "id": 6,
      "title": "Sambata Don",
      "icon": "http://<host>/media/music/icons/sambata_icon.png",
      "cover": "http://<host>/media/music/covers/sambata.png",
      "color": "4B1D5A",
      "song_ids": [125, 126, 127],
      "is_remote": true
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:00:00.123"
}
```

---

### POST `/api/music/playlists/`

Create a playlist. `id` auto-assigned, `is_remote` forced to `true`, `created_by` set to
the caller. Songs are stored in the order given (`PlaylistSong.position` = list index).

**Permission:** `IsAdmin` · **Content-Type:** `application/json` or `multipart/form-data`

#### Request

| Field      | Type             | Required | Description                                                                                                                                    |
| ---------- | ---------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `title`    | string           | Yes      | Max 255 chars                                                                                                                                  |
| `icon`     | string           | Yes      | URL from `POST /api/upload-file/` (same rules as song `thumb`; explicit null accepted)                                                         |
| `cover`    | string           | Yes      | URL from `POST /api/upload-file/` (same rules; explicit null accepted)                                                                         |
| `color`    | string           | No       | Max 8 chars, must match `^[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$` (no `#`); blank allowed                                                           |
| `song_ids` | array of integer | No       | Ordered ids of existing, non-deleted songs (bundled or remote). Empty list allowed. In multipart, repeat the key (`song_ids=1&song_ids=5`). **Must not contain duplicates** (see errors). |

```json
{
  "title": "My Mix",
  "icon": "http://<host>/media/uploads/a1b2c3d4e5f60718293a4b5c6d7e8f90.png",
  "cover": "http://<host>/media/uploads/0f9e8d7c6b5a49382716f5e4d3c2b1a0.png",
  "color": "6A1B9A",
  "song_ids": [1, 5, 166]
}
```

#### Example JSON Response (`201 Created`)

```json
{
  "data": {
    "id": 10,
    "title": "My Mix",
    "icon": "http://<host>/media/uploads/a1b2c3d4e5f60718293a4b5c6d7e8f90.png",
    "cover": "http://<host>/media/uploads/0f9e8d7c6b5a49382716f5e4d3c2b1a0.png",
    "color": "6A1B9A",
    "song_ids": [1, 5, 166],
    "is_remote": true
  },
  "message": "",
  "status": 201,
  "time": "2026-09-23T10:00:00.123"
}
```

#### Error Responses

| Status                      | When / literal message                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------- |
| `400 Bad Request`           | Missing `title`/`icon`/`cover`: `"This field is required."`                                             |
| `400 Bad Request`           | `icon`/`cover` invalid: same three `UploadedFileURLField` messages as song `thumb`                      |
| `400 Bad Request`           | `color` fails the regex: `"Enter a valid value."`; longer than 8: `"Ensure this field has no more than 8 characters."` |
| `400 Bad Request`           | `song_ids` contains an unknown or soft-deleted id: `"Unknown song ids: [999, 1000]"`                    |
| `400 Bad Request`           | Non-integer entry in `song_ids`: `"A valid integer is required."`                                       |
| `500 Internal Server Error` | Duplicate id in `song_ids` — violates `unique_together (playlist, song)` on bulk insert; not validated (and not wrapped in a transaction on create, so the playlist row itself may already be saved) |
| `401 Unauthorized`          | No/invalid token                                                                                        |
| `403 Forbidden`             | `"Admin access required."`                                                                              |

---

### GET `/api/music/playlists/{id}/`

Retrieve one non-deleted playlist. **Permission:** `IsAuthenticatedUser`. `data` is a
single playlist object. `404` (`"No Playlist matches the given query."`) if missing or
soft-deleted.

---

### PUT `/api/music/playlists/{id}/`

Full replace. **Permission:** `IsAdmin` · JSON or multipart. `title`, `icon`, `cover` are
required again. `song_ids` stays optional: if present (including `[]` in JSON) it
**replaces** the whole ordered set (all existing `PlaylistSong` rows are deleted and
re-created); if omitted, the existing songs are left unchanged. To clear a playlist, send
JSON `"song_ids": []` (an empty list cannot be expressed in multipart). Returns `200`
with the read shape. `is_remote` is not changed.

---

### POST `/api/music/playlists/{id}/update/`

Partial update. **Permission:** `IsAdmin` · JSON or multipart. Any subset of `title`,
`icon`, `cover`, `color`, `song_ids`; `song_ids`, when present, replaces the full ordered
set. Returns `200` with the read shape.

---

### DELETE `/api/music/playlists/{id}/`

Soft delete (`is_deleted = true`, `deleted_at = now()`); `PlaylistSong` rows are kept.
**Permission:** `IsAdmin`. Returns `204 No Content`.

---

### `seed_music` management command

```
python manage.py seed_music [--songs PATH] [--playlists PATH]
                            [--remote-playlists "4,5,6,7,8,9"] [--app-root PATH]
```

Imports the Flutter app's bundled catalogue into the DB with the **same integer ids**,
so API-created rows continue from the next id. Runs in a single transaction and is
idempotent (`update_or_create` by id).

| Option               | Default                             | Description                                                                                                  |
| -------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `--songs`            | `music/seed_data/songs.json`        | Array of `{id, title, artist, thumb, asset, duration}`                                                       |
| `--playlists`        | `music/seed_data/playlists.json`    | Array of `{id, title, icon, cover, color, song_ids}`                                                         |
| `--remote-playlists` | `4,5,6,7,8,9`                       | Playlist ids to seed as remote. Empty string = everything bundled. Unknown ids abort with `--remote-playlists names unknown playlist ids: [...]` |
| `--app-root`         | none                                | Flutter project root, used to copy `assets/...` media for remote rows into `MEDIA_ROOT` (`music/audio`, `music/thumbs`, `music/icons`, `music/covers`, with sanitised filenames). Only needed until the files are in `MEDIA_ROOT`; existing files are reused. |

Behavior:
- A song is seeded remote only if every playlist containing it is remote; otherwise it
  keeps its `assets/...` refs.
- Remote rows get `*_file` set and `*_ref` cleared; bundled rows the reverse.
- Each playlist's `PlaylistSong` rows are deleted and re-created from `song_ids`.
- Prints counts (songs/playlists remote vs bundled, media copied vs reused), warnings for
  media that couldn't be found (`no media for <ref>: ...`), and `Next song id: N | Next playlist id: M`.

---

## Schema & Documentation

| Endpoint | Permission | Description |
| --- | --- | --- |
| `GET /schema/` | Public (drf-spectacular default `AllowAny`) | OpenAPI 3 schema generated by `drf_spectacular` (`SpectacularAPIView`). Default response format is **YAML** (`application/vnd.oai.openapi`); request JSON with `?format=json` or `Accept: application/vnd.oai.openapi+json` / `application/json` |
| `GET /docs/` | Public | Swagger UI (`SpectacularSwaggerView`) using the project template `templates/swagger-ui.html` (dark theme, `swagger-ui-dist@3.52.5` from jsDelivr), pointed at `/schema/` |
| `/admin/` | Django admin login (`is_staff` users; log in with `phone_number` + password) | Django admin site. `core` registers `DailyRequestCount` (read-only list of `date`, `count`, newest first, adding disabled) |

Notes: `SPECTACULAR_SETTINGS = {"SCHEMA_PATH_PREFIX": r"/api/v[0-9]"}` — no route actually uses an `/api/vN` prefix, so the setting has no effect on path trimming. `HEAD /api/health/` is a plain Django view and does not appear in the schema. `/schema/` and `/docs/` are excluded from the request counter.

---

## 14. Notifications

The `notifications` app has two independent parts:

1. **`NotificationTemplate` model + REST API** (`/api/notifications/templates/`) — user-authored
   message templates (plain text) stored in the DB.
2. **`notifications/templates.py` + `notifications/services.py`** — hard-coded Python
   message templates and helpers that render them into SMS text or a WhatsApp `wa.me`
   link.

The two are **not connected**: the DB templates are not rendered by `services.py`, and
`services.py` never reads the DB.

**The backend sends nothing.** There is no FCM / push / APNs integration, no SMS or
WhatsApp gateway, no device-token model or registration endpoint, no signals, no
scheduled job, and no in-app notification inbox. Delivery is done by the client (the
Flutter app opens a `wa.me` / `sms:` link itself).

---

### Template categories

`category` is one of exactly four values (`NotificationCategory`):

| Value       | Label     |
| ----------- | --------- |
| `general`   | General (default) |
| `promotion` | Promotion |
| `alert`     | Alert     |
| `reminder`  | Reminder  |

### Visibility / gym scoping

- **Admin**-created templates get `gym = null` → global, visible to admins and every gym owner.
- **Gym owner**-created templates get `gym = request.user.gym_details` → visible to that gym owner (and admins).
- Admin sees all non-deleted templates; a gym owner sees `gym == own gym_details` **or** `gym is null`.
- `gym` is read-only; it is always derived server-side and ignored if sent.
- There is no per-object ownership check beyond this queryset filter. Consequently a
  **gym owner can also `PUT` / `POST .../update/` / `DELETE` global admin templates**
  (they're in the owner's queryset). A gym owner whose `gym_details` is null creates a
  template with `gym = null`, i.e. a global template visible to every gym owner.

### Permission

`IsAdminOrGymOwner` for every action (`user_type` in `admin`, `gym_owner`). Unauthenticated
→ `401` `"Authentication credentials were not provided."`; trainer/member → `403`
`"Admin or Gym Owner access required."`

Soft-deleted templates are excluded from all actions (`404` on retrieve/update/delete).

---

### GET `/api/notifications/templates/`

List templates visible to the caller. Always paginated (`CustomPagination`).

**Permission:** `IsAdminOrGymOwner`

**Query parameters:**

| Param       | Type    | Required | Description                                                                                         |
| ----------- | ------- | -------- | --------------------------------------------------------------------------------------------------- |
| `category`  | string  | No       | Exact match on category. Not validated — an unknown value just returns an empty list                |
| `search`    | string  | No       | Case-insensitive contains match on `title` or `message`                                             |
| `ordering`  | string  | No       | `created_at`, `title`, `-created_at`, `-title` (comma-separate for multiple). Default `-created_at` |
| `page`      | integer | No       | Page number (default `1`); out of range → `404` `"Invalid page."`                                   |
| `page_size` | integer | No       | Default `20`, max `100`                                                                             |

#### Response (`data[]`)

| Field        | Type             | Description                                         |
| ------------ | ---------------- | --------------------------------------------------- |
| `uuid`       | string (UUID)    | Template id                                         |
| `gym`        | string \| null   | Owning gym's UUID; `null` for a global template     |
| `gym_name`   | string \| null   | Owning gym's `name`; `null` for a global template   |
| `title`      | string           | Max 255 chars                                       |
| `message`    | string           | Message body (free text; not rendered/interpolated by the server) |
| `category`   | string           | `general` / `promotion` / `alert` / `reminder`      |
| `created_at` | datetime (ISO 8601, UTC) |                                             |
| `updated_at` | datetime (ISO 8601, UTC) |                                             |

#### Example JSON Response

```json
{
  "data": [
    {
      "uuid": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
      "gym": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
      "gym_name": "Iron Paradise",
      "title": "Festive Discount",
      "message": "Get 20% off on your next membership renewal this week only.",
      "category": "promotion",
      "created_at": "2026-09-21T09:30:00.000000Z",
      "updated_at": "2026-09-21T09:30:00.000000Z"
    },
    {
      "uuid": "8b1e2f3a-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
      "gym": null,
      "gym_name": null,
      "title": "Membership Renewal Reminder",
      "message": "Hi! Your membership is expiring soon. Renew now to keep enjoying uninterrupted access.",
      "category": "reminder",
      "created_at": "2026-09-20T10:00:00.000000Z",
      "updated_at": "2026-09-20T10:00:00.000000Z"
    }
  ],
  "message": "",
  "status": 200,
  "time": "2026-09-23T10:00:00.123",
  "count": 2,
  "next": null,
  "previous": null
}
```

---

### POST `/api/notifications/templates/`

Create a template. `gym` and `created_by` are set server-side.

**Permission:** `IsAdminOrGymOwner` · JSON or form data

#### Request

| Field      | Type   | Required | Description                                                         |
| ---------- | ------ | -------- | ------------------------------------------------------------------- |
| `title`    | string | Yes      | Max 255 chars, non-blank                                            |
| `message`  | string | Yes      | Non-blank text                                                      |
| `category` | string | No       | One of the four values; defaults to `general` (model default)       |

```json
{
  "title": "Festive Discount",
  "message": "Get 20% off on your next membership renewal this week only.",
  "category": "promotion"
}
```

#### Example JSON Response (`201 Created`)

```json
{
  "data": {
    "uuid": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
    "gym": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    "gym_name": "Iron Paradise",
    "title": "Festive Discount",
    "message": "Get 20% off on your next membership renewal this week only.",
    "category": "promotion",
    "created_at": "2026-09-21T09:30:00.000000Z",
    "updated_at": "2026-09-21T09:30:00.000000Z"
  },
  "message": "",
  "status": 201,
  "time": "2026-09-21T09:30:00.456"
}
```

#### Error Responses

| Status             | When / literal message                                                     |
| ------------------ | -------------------------------------------------------------------------- |
| `400 Bad Request`  | Missing `title`/`message`: `"This field is required."`; blank: `"This field may not be blank."` |
| `400 Bad Request`  | Bad category: `"\"<value>\" is not a valid choice."`                       |
| `400 Bad Request`  | `title` > 255: `"Ensure this field has no more than 255 characters."`      |
| `401 Unauthorized` | No/invalid token                                                           |
| `403 Forbidden`    | `"Admin or Gym Owner access required."`                                    |

---

### GET `/api/notifications/templates/{uuid}/`

Retrieve one template within the caller's visible set. **Permission:** `IsAdminOrGymOwner`.
`404` `"No NotificationTemplate matches the given query."` if not visible, soft-deleted, or missing.

---

### PUT `/api/notifications/templates/{uuid}/`

Full update. **Permission:** `IsAdminOrGymOwner`. `title` and `message` required,
`category` optional (if omitted on PUT, the existing value is kept — DRF skips
non-required fields that aren't sent). Sets `updated_by` to the caller. `gym` is not
changed. Returns `200` with the template object.

---

### POST `/api/notifications/templates/{uuid}/update/`

Partial update (POST-instead-of-PATCH). **Permission:** `IsAdminOrGymOwner`. Any subset of
`title`, `message`, `category`. Sets `updated_by`. Returns `200` with the template object.

---

### DELETE `/api/notifications/templates/{uuid}/`

Soft delete via `BaseModel.soft_delete(deleted_by=request.user)` (sets `is_deleted`,
`deleted_at`, `updated_by`). **Permission:** `IsAdminOrGymOwner`. Returns `204 No Content`.

---

### Server-side message templates (`notifications/templates.py`)

A static `TEMPLATES: dict[str, str]` of Python `str.format()` strings, keyed by event name.
These are **not** the DB `NotificationTemplate` rows and are not exposed over HTTP.

| Key                  | Intended event (per code comment)              | Placeholders                                    | Text |
| -------------------- | ---------------------------------------------- | ----------------------------------------------- | ---- |
| `membership_expiry`  | Membership about to expire                     | `name`, `gym_name`, `expiry_date`, `days_left`  | `Hi {name}, your membership at {gym_name} expires on {expiry_date} ({days_left} day(s) left). Please renew to keep training with us.` |
| `membership_expired` | Membership has already expired                 | `name`, `gym_name`, `expiry_date`               | `Hi {name}, your membership at {gym_name} expired on {expiry_date}. Please renew your membership to continue your fitness journey.` |
| `absent_reminder`    | Member absent for too many days                | `name`, `gym_name`, `days`                      | `Hi {name}, we miss you at {gym_name}! You haven't visited in {days} day(s). Come back and keep going strong!` |
| `payment_received`   | After a payment is recorded                    | `name`, `amount`, `gym_name`, `end_date`        | `Hi {name}, we received a payment of Rs. {amount} at {gym_name}. Your membership is now active till {end_date}. Thank you!` |
| `welcome_member`     | New member joins the gym                       | `gym_name`, `name`, `trainer_name`              | `Welcome to {gym_name}, {name}! Your trainer is {trainer_name}. We look forward to your fitness journey with us!` |
| `trainer_assigned`   | Member assigned/reassigned to a trainer        | `name`, `trainer_name`, `gym_name`              | `Hi {name}, you have been assigned to trainer {trainer_name} at {gym_name}. Reach out to your trainer for your personalised schedule.` |

### Delivery helpers (`notifications/services.py`)

| Function                                              | Returns                                                                                   |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `render_message(template_name, context)`              | Filled-in string. Raises `ValueError("Unknown notification template: '<name>'")` for an unknown key, or `ValueError("Template '<name>' is missing context key '<key>'")` if a placeholder is missing from `context`. Extra context keys are ignored. |
| `build_whatsapp_url(phone_number, message)`           | `https://wa.me/<digits>?text=<url-encoded message>` — strips whitespace, a leading `+`, spaces and `-` from the number (no other normalisation; no country code is added) |
| `get_whatsapp_url(phone_number, template_name, context)` | `render_message` + `build_whatsapp_url`; logs `WhatsApp link built — to=<phone> template=<name>` at INFO |
| `get_sms_text(template_name, context)`                | `render_message` result; logs `SMS text rendered — template=<name>` at INFO               |

### Trigger points

**None.** A repository-wide search finds no imports of `notifications.services` or
`notifications.templates` outside the `notifications` app, and no calls to
`render_message`, `get_whatsapp_url`, `get_sms_text` or `build_whatsapp_url`. No
membership, payment, attendance or trainer-assignment code path renders or returns
these messages, and no API response includes a `wa.me` link generated by the server.
The helpers are currently unused scaffolding; the "intended event" column above only
reflects the code comments in `templates.py`.

---

## 15. Known Issues & Implementation Notes

These were found while rebuilding this document from the code. Read them before relying on or changing these areas. Each endpoint section above has more detail.

### 15.1 Bugs that break or corrupt data

- **`POST /api/payments/` returns HTTP 500 even when it succeeds** ([§8](#8-member-payments-phase-3)). `MemberPaymentResponseSerializer.amount` has no `source`, so building the response raises `AttributeError`. By then the `Membership` row is already created and the member's tracking fields are already updated. A client that retries after the 500 creates a duplicate membership, because this endpoint doesn't run the overlap check.
- **An empty workout or body-measurement upload deletes all of that user's server data** ([§11](#11-backup--sync)). If `sessions` or `measurements` is missing or `[]`, the user's existing server rows are hard-deleted and nothing replaces them.
- **Backup upload changes are not atomic** (`POST /api/backup/upload/`). Each item in `changes` is saved on its own, so if a later item fails, the earlier ones stay saved.
- **Duplicate `song_ids` in a playlist write cause a 500** ([§13](#13-music-playlists--songs)). On create, the playlist row may already be saved when the error happens.
- **Some bad query parameters cause 500s instead of 400s:**
  - `days` that isn't an integer (reports)
  - malformed `user_id` or `date` (attendance list)
  - malformed `member_id` (`GET /api/payments/`, likely)
  - malformed `user_id` (backup download)

### 15.2 Authorization and scoping gaps

- **Permission classes only check `user_type`, never `status`.** A user who is disabled, suspended or soft-deleted after logging in keeps full access until their access token expires (24 h by default). Changing a password doesn't revoke existing tokens either. Logout only blacklists the refresh token, and doesn't check that the token belongs to the caller.
- **Login checks account status before the password.** A 403 "disabled/suspended/deleted" response therefore reveals that a phone number is registered, even when the password is wrong.
- **Membership writes aren't limited to the owner's gym** ([§6](#6-memberships)). A gym owner can create or reassign memberships for any member, including members of other gyms and soft-deleted members. Reads are limited to the owner's gym.
- **Attendance backup sync (`/api/backup/upload/`, `/api/backup/download/`) isn't limited to a gym.** Any admin, gym owner or trainer can read or write any gym's attendance, and a download without `user_id` returns every gym's data. This path also skips the check-in rules: the 50 m distance check, the duplicate check and the photo requirement.
- **Gym owners can edit and delete global (admin-created) notification templates** ([§14](#14-notifications)). Nothing checks who owns a template on write.
- **The member `trainer` filter and `assign-trainer` accept trainers from other gyms or disabled trainers** ([§3](#3-user-management)).
- **Most reports aren't available to trainers.** They can only call `GET /api/reports/inactive-members/` (`IsGymOwner | IsTrainer`). The other reports require `IsGymOwner`, `IsAdmin`, or `IsAdmin | IsGymOwner`.

### 15.3 Behaviour that differs from what you might expect

- **Error `message` isn't always a string.** For validation errors, both `data` and `message` hold the field-error dict ([Conventions](#standard-response-envelope)).
- **`gym_id` on trainer/member records is the gym owner's user UUID, not the `Gym` record's UUID.** Only `gym_uuid` on `/auth/profile/` refers to the `Gym` master record.
- **Some responses return image URLs as relative `/media/...` paths instead of absolute URLs:**
  - `enable`, `disable` and `assign-trainer` in [§3](#3-user-management)
  - photos in attendance responses
- **Nothing sets a membership to `expired`.** No scheduled job exists, and `membership-expiry` reads the user's `membership_end` field rather than the `Membership` table.
- **No API creates `Payment` rows.** `/payments/` is read-only, and rows only come from the Django admin or fixtures.
- **Payment `mode` casing differs:** the model uses `cash`/`online`, but `POST /api/payments/` accepts `Cash`/`Online`.
- **Soft deletes don't cascade:**
  - A deleted gym leaves its owner in place.
  - A deleted owner leaves their trainers and members in place.
  - A deleted trainer stays linked to members through `trainer_id`.
  - Deleted songs keep their playlist links.
  - There is no API to restore deleted users.
- **Backup sync semantics** ([§11](#11-backup--sync)):
  - `since` is inclusive (`>=`), and an unparseable value is silently ignored.
  - Downloads never include deleted rows, so clients can't learn about deletions from the server.
  - The server stores its own save time as `updated_at`, not the client's timestamp.
  - A timestamp without a timezone offset makes that item fail.
- **Most "today" and date-boundary logic is UTC** (`TIME_ZONE = "UTC"`). This covers:
  - the one-check-in-per-day rule
  - report windows
  - the `api-requests-today` counter
- **Check-in/out timestamps come from the client and aren't validated.** Checkout isn't checked to be later than check-in.
- **Notifications are never sent.** The server has no push notifications (FCM or otherwise), no device-token registration, and no SMS/WhatsApp gateway. `notifications/services.py`/`templates.py` only render text or `wa.me` links, and nothing in the repo calls them. The `NotificationTemplate` CRUD API only stores templates.
- **`HEAD /api/health/` returns 405 for `GET`.** Uptime monitors must send `HEAD`.

### 15.4 Code / config housekeeping

- `core/permissions.py::HavePermissions`, listed in earlier versions of this doc, no longer exists.
- The code comment in `fit_&_fuel/urls.py` refers to `/auth/me/`, but the actual route is `/auth/profile/`.
- `music/models.py` and `music/seed_data/README.md` say 138 songs / 7 playlists, but the seed data has 165 / 9.
- `SPECTACULAR_SETTINGS["SCHEMA_PATH_PREFIX"]` (`/api/v[0-9]`) matches no route.

### 15.5 Core implementation notes

- **Envelope is per-view, not global.** `DEFAULT_RENDERER_CLASSES` isn't set; the envelope only exists because all DRF views inherit from `core.views` base classes (or set `renderer_classes` explicitly, as `LoginView`/`TokenRefreshAPIView` do). A new view that subclasses a DRF class directly will return raw DRF JSON (plus the browsable API).
- **`/api/my-ip/` uses no envelope** (`renderers.JSONRenderer` is plain DRF `JSONRenderer` re-exported via `from rest_framework.renderers import JSONRenderer` in `core/renderers.py`).
- **Error `message` is not always a string.** For validation errors the renderer copies the whole error dict (or list) into both `data` and `message`.
- **Extra keys in `detail`-style errors are dropped.** When a non-2xx body has `detail`, `data` becomes `null`, so SimpleJWT's `code` (`token_not_valid`, `user_inactive`, …) and `messages` never reach the client, and `/api/my-ip/`-style `{"ip", "detail"}` bodies would lose `ip` if they went through the renderer.
- **Odd `307` branch in the renderer.** For an error dict with a truthy `status` key, the renderer evaluates `data["status"][0].code` and, if it equals the integer `307`, rewrites `data`/`status`. Nothing in the codebase raises such an error (DRF `ErrorDetail.code` is a string). Side effect: a validation error on a field literally named `status` is fine (`ErrorDetail` has `.code`), but if `data["status"]` were a nested dict or a plain `str` list this line would raise and turn the response into a 500.
- **2xx string substring check.** `"results" in data and "count" in data` is evaluated on strings too — a success string containing both words would be treated as a paginated dict and raise.
- **Envelope `time` is naive.** `datetime.datetime.now()` has no timezone. On Linux Django sets the process TZ to `TIME_ZONE` (UTC) so it will be UTC; on Windows hosts it is the machine's local time. Model datetimes, by contrast, carry `Z`.
- **`204` responses carry an envelope body** (renderer always emits one).
- **`HEAD /api/health/` rejects `GET` with 405.** Monitors that only issue `GET` will see the service as unhealthy.
- **Request counter writes to the DB on every request**, before auth, including health checks, `OPTIONS` preflights and 404s, and for non-`/api/` routes such as `/auth/`, `/gyms/`, `/users/`. A DB outage therefore fails every request, including the health check.
- **Upload validation order/robustness.** The extension is taken from the client filename and checked separately from Pillow's content check, so e.g. a GIF named `x.png` passes and is stored as `.png`. The 5 MB check runs after the whole file has been received and parsed; there is no global request-size cap, so very large uploads are fully accepted to a temp file before being rejected.
- **Uploaded files are never garbage-collected**; replacing an image field leaves the old file and any unused upload in `media/uploads/`.
- **`UploadedFileURLField` accepts any existing media file**, regardless of URL host or which user uploaded it, and regardless of subfolder (e.g. an existing `profile_pictures/…` path). Paths are not normalised before `default_storage.exists()`; a crafted `/media/../…` value would likely raise `SuspiciousFileOperation` (→ 500) rather than a clean 400 (not verified).
- **Absolute URLs follow the incoming request's scheme/host.** No `SECURE_PROXY_SSL_HEADER` / `USE_X_FORWARDED_HOST` is set, so behind a TLS-terminating proxy, `upload-file` and image fields return `http://` URLs (and the proxy's upstream host if `Host` isn't forwarded).
- **Media and static are served by Django in production** (`serve` view when `DEBUG` is off) — works, but Django docs discourage it for performance/security.
- **`GEOIP_PATH` is relative** (`static/geo_lite2/GeoLite2-City.mmdb`), resolved against the working directory; the database file isn't in the repo. If it's missing, `/api/my-ip/` returns `400 "Unable to get IP location: …"` for every call.
- **Permissive defaults:** `ALLOWED_HOSTS = ["*"]`, `CORS_ALLOW_ALL_ORIGINS = True`, no throttling at all (including on login).
- **`JWT_SECRET_KEY` / `SECRET_KEY` have no fallback.** If `JWT_SECRET_KEY` is unset, `SIGNING_KEY` is `None` and token issuance/verification fails.
- **`IsAuthenticatedUser`'s custom message is effectively unreachable** (unauthenticated callers get DRF's 401 `NotAuthenticated` text); grep shows it isn't referenced outside `core/permissions.py` either.
- **No object-level permissions** in any `core` permission class — all tenant scoping is in view querysets.
- **`BaseModel.objects` includes soft-deleted rows**; only `active_objects` filters them. Views must opt in explicitly.
- **Logging config quirks:** the `errors` file handler has no level, so `errors.log` receives every DEBUG-level record from the root logger (same as `logs.log`); the `sql` and `system-error` handlers are defined but not attached to any logger.
- **`SPECTACULAR_SETTINGS["SCHEMA_PATH_PREFIX"]` (`/api/v[0-9]`) matches no route** — leftover setting.
- **`core/utils.py` helpers** (`haversine_distance_m`, `mail_letter_sender`) are internal; `mail_letter_sender` swallows all exceptions with `print(e)`, so email failures are silent to callers.
- **Payment mode casing mismatch:** model enum `PaymentMode` is `cash`/`online`; `MemberPaymentSerializer.mode` accepts `Cash`/`Online`.
