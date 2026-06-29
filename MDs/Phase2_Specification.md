# Phase 2 Specification — Gym & Member Management API

## Mandatory Analysis

Before implementing anything, inspect the existing backend project and follow its:

- folder structure
- app organization
- coding conventions
- base models
- serializers
- viewsets
- URL routing
- response format
- exception handling
- pagination
- authentication utilities
- admin configuration

Reuse existing architecture. Do not replace it.

**Overview:** In Phase 2 we build out the gym-owner and trainer management features. This includes CRUD APIs for **Trainers**, **Members**, **Memberships**, and **Payments**, plus endpoints for trainers to list and view their assigned members. All new code must follow the existing backend architecture: use the `core.models.BaseModel` (with soft-delete fields) for new models, the `core.renderers.ResponseRenderer` for JSON envelopes, and the `core.pagination.CustomPagination` (with `page`/`page_size`) for list endpoints. Permission logic should use the custom classes in `core.permissions` (e.g. `IsGymOwner`, `IsTrainer`) and view/query filtering so that gym owners only see their own users and trainers only see their assigned members.

- **Data Source:** All data remains local-by-default (SQLite) and is **not** deleted on logout. We treat the backend as a **persistent backup**. Gym-owner actions (create/update users, memberships, etc.) are always saved. The existing token/session logic from Phase 1 is reused (no change to offline behavior).

- **Response Envelope:** All API responses must use the existing JSON envelope. Every response is an object with keys:

  ```json
  {
    "data": <object or list or null>,
    "message": "<string>",
    "status": <HTTP status code>,
    "time": "<ISO timestamp>"
  }
  ```

  For paginated lists, include `"count"`, `"next"`, and `"previous"` in the envelope (handled by `ResponseRenderer` & `CustomPagination`).

- **Pagination & Filtering:** All list endpoints must support `?page=` and `?page_size=` query parameters (max 100 by default). Trainers and members lists must support search filters on phone number, first name, or last name. Use DRF’s `SearchFilter` or `django-filter` as in the base project (e.g. `filter_backends = [DjangoFilterBackend, SearchFilter]` with `search_fields = ['first_name','last_name','phone_number']`).

## 1. Database Models

### 1.1 CustomUser (existing)

We extend the existing `accounts.CustomUser` model **in-place**. No new user table is needed for this phase, but we add fields:

- **`trainer_limit`** (IntegerField, default 0).
  - Only applies to gym owners. This field tracks the allowed number of trainers for a gym (for future billing logic). On creating new trainers, the system should check that the current trainer count does not exceed this limit; otherwise return a 400 error. (For now we can simply store this field and enforce in the viewset.)
- **Existing fields:** Already present fields include `phone_number` (unique, login), `first_name`, `last_name`, `date_of_birth`, `gender`, `profile_picture`, `user_type` (choices: ADMIN / GYM_OWNER / TRAINER / MEMBER), `status` (ACTIVE / DISABLED / SUSPENDED / DELETED), `gym` (FK to a GymOwner user), and `trainer` (FK to a Trainer user). We will continue using `gym` to link trainers and members to their gym owner, and `trainer` on members to track assignment.

**Business rules:** When a gym owner creates a trainer or member, set the new user’s `gym` field to point to the gym owner (owner’s UUID). Trainers’ `gym` is the owner; members’ `gym` is the owner and `trainer` can be set if assigned immediately. Only gym owners (or Admin) may create/update trainers and members. Trainers may only see (via API) members where `trainer = their UUID` and `status = ACTIVE`. Members themselves have no new server-facing actions in this phase beyond standard profile viewing (their workout logging is offline-only).

### 1.2 Membership (new model)

We create a new model **`Membership`** for tracking each member’s gym membership period and payment info. Fields should include:

- **`uuid`** (UUIDField, primary key) — unique identifier.
- **`member`** (ForeignKey to `CustomUser`, `limit_choices_to={'user_type': MEMBER}`) — the user this membership belongs to.
- **`start_date`** (DateField) — membership start (inclusive).
- **`end_date`** (DateField) — membership end (inclusive). The business logic is that membership lasts until midnight of `end_date`.
- **`plan`** (CharField, optional) — e.g. "Monthly", "Quarterly", etc. _Optional comment:_ the owner may select a predefined plan as a convenience, but **the actual duration is determined by `start_date`/`end_date`**, not by a fixed-day interval. If no plan is selected, this field can be null/blank.
- **`amount_paid`** (DecimalField) — total amount paid for this membership term.
- **`payment_mode`** (CharField, choices: CASH / ONLINE) — how the member paid.
- **`status`** (CharField) — e.g. ACTIVE or EXPIRED. This can be a computed or updated field (for simplicity, set ACTIVE on create; future logic can mark it expired once past the end date).
- **Audit fields:** `created_by`, `updated_by`, `created_at`, `updated_at`, `is_deleted`, `deleted_at` (inherited from `BaseModel`).

**Relationships:** A `Membership` is linked to exactly one Member. A Member can have multiple `Membership` records over time (for renewals). Gym owners only create **one active membership at a time**; they may create a new one when renewing.

### 1.3 Payment (new model)

We also create a **`Payment`** model to record each payment transaction. Fields:

- **`uuid`** (UUIDField, PK).
- **`membership`** (ForeignKey to `Membership`) — the membership this payment is for.
- **`amount`** (DecimalField) — payment amount (should match or be ≤ `membership.amount_paid` for that term).
- **`mode`** (CharField, choices: CASH / ONLINE).
- **`paid_on`** (DateTimeField) — timestamp of payment (auto-set to now if not provided).
- **Audit fields:** `created_by`, `updated_by`, etc.

**Relationships:** Each `Payment` belongs to one membership term. A membership may have multiple payments (e.g. installment, renewal). If the owner records a payment at the time of creating the membership, both objects should be created together.

## 2. Serializers

Follow the existing pattern in `accounts/serializers.py` and `core.serializers.py` (if any). All serializers should inherit from DRF’s `ModelSerializer` and use the `renderers.ResponseRenderer` envelope automatically via the view. Include the relevant fields and validation.

### 2.1 User Serializers

We already have serializers for `CustomUser` in Phase 1. For Phase 2, add or adjust:

- **`TrainerSerializer`** (for creating/updating GymOwner’s trainers). Fields:
  - `uuid`, `phone_number`, `first_name`, `last_name`, `gender`, `profile_picture`, `status`.
  - **Do not** allow setting `user_type` (force it to TRAINER in `create()`).
  - Include `password` field write-only for setting initial password. Owner will set a password when creating a trainer.
  - Exclude `gym` (the view will set `gym=request.user`) and `trainer` (n/a for trainers).
  - Make `phone_number` required & unique; use Django validators to ensure uniqueness.
  - On update, allow changing name, status, and password (if provided). If password is changed, hash it using `set_password()`.
  - Example usage:
    ```json
    // Create Trainer request
    {
      "phone_number": "9876501234",
      "first_name": "Alice",
      "last_name": "Doe",
      "password": "Passw0rd!"
    }
    ```

- **`MemberSerializer`** (for GymOwner’s members). Fields:
  - `uuid`, `phone_number`, `first_name`, `last_name`, `gender`, `profile_picture`, `status`, `trainer` (UUID of assigned trainer), plus membership summary (see below).
  - On create, similar to `TrainerSerializer`, include `password`.
  - Include `trainer` field writeable to assign a trainer at creation or update (UUID of an existing trainer in this gym). Validate that the trainer belongs to the same gym.
  - **Exclude** `gym` (will be set automatically), and `user_type` (force to MEMBER).
  - **Membership**: The `MemberSerializer` should _optionally_ accept nested membership info on creation or update (if we want to allow one-call membership setup). For simplicity, we can leave membership as a separate API (see below), but the response for a member detail should include their latest active membership (see section 2.2).

- **`MembershipSerializer`**. Fields:
  - `uuid`, `member` (UUID of user), `start_date`, `end_date`, `plan` (optional), `amount_paid`, `payment_mode`, `status`.
  - Validate: `start_date <= end_date`.
  - On create/update, ensure `member` refers to a user of type MEMBER. Also, ensure that no two ACTIVE memberships overlap for the same member (business rule: a member cannot have two active memberships with overlapping dates).
  - Default `status` to ACTIVE on create.

- **`PaymentSerializer`**. Fields:
  - `uuid`, `membership` (UUID), `amount`, `mode`, `paid_on`.
  - Validate: `membership` exists and belongs to the same gym owner. Check `amount > 0`.
  - Set `paid_on` to now if not provided.

- **Note:** In serializers’ `create()` methods, set the `created_by = request.user` and `updated_by = request.user` appropriately. Use the base project’s conventions (they likely use `perform_create` in views or override `serializer.save(created_by=self.request.user)`).

## 3. Views and API Endpoints

All views should extend the base classes in `core.views` (e.g. `BaseModelViewSet`) and should be routed using DRF routers as in Phase 1. The root paths use the existing `accounts/urls_users.py`, `urls_trainer.py`, `urls_member.py` conventions. Ensure that each view’s `permission_classes` restrict access appropriately.

### 3.1 Gym Owner (Admin) Endpoints

_Gym Owners and the Platform Admin use these endpoints._ In practice, Admin (you) can manage any user, and each gym owner can manage **only their own** trainers and members. We will implement filtering in the querysets to enforce this. Use `IsAdminOrGymOwner` permission (allowing both roles).

- **Trainers** (`TrainerViewSet`):
  - **POST** `/users/trainers/` – Create a new Trainer. Requires `phone_number`, `first_name`, `last_name`, and `password`. The view should set `user_type=TRAINER` and `gym=request.user` on the new user. Return 201 with the trainer object.
  - **GET** `/users/trainers/` – List all trainers for this gym. (Admin sees all gyms’ trainers; a gym owner sees only their trainers where `gym = self`). Support `?search=` by name/phone.
  - **GET** `/users/trainers/{trainer_uuid}/` – Retrieve trainer details. Only if the trainer belongs to the same gym (or if Admin). Return 404 if not found.
  - **PUT** `/users/trainers/{trainer_uuid}/` – Update trainer (full replace). Allow changing name, `status` (to disable/enable), and optionally password. Do **not** allow changing `phone_number` to collide with another user. Disallow changing `gym` (it stays with the owner).
  - **DELETE** `/users/trainers/{trainer_uuid}/` – _Soft-delete_ (set `status = DISABLED` or `is_deleted = true`). The base project uses `is_deleted`. Instead of actual deletion, respond with 204 and mark trainer deleted. If using `is_deleted`, the object will no longer appear in queries. (Alternatively, reuse `status = DISABLED` as done in Phase 1 for users – either approach is acceptable as long as it matches base practice.)

- **Members** (`MemberViewSet`):
  - **POST** `/users/members/` – Create a new Member. Required fields: `phone_number`, `first_name`, `last_name`, `password`. The view sets `user_type=MEMBER` and `gym=request.user`. The request may include an optional `"trainer": "<trainer_uuid>"` to assign a trainer immediately (validate that trainer exists and belongs to the gym).
  - **GET** `/users/members/` – List all members of this gym. (Admin sees all; a gym owner sees only members with `gym = self`.) Support search by name/phone and filtering by `status`.
  - **GET** `/users/members/{member_uuid}/` – Get details of a member. Include their current trainer (UUID) and membership summary (see **Memberships** below). Only return if `member.gym = self`.
  - **PUT** `/users/members/{member_uuid}/` – Update member. Allow changing name, `status` (disable/enable), `trainer` (re-assign). If `trainer` changes to null, the member is unassigned. Do **not** allow changing `phone_number` here.
  - **DELETE** `/users/members/{member_uuid}/` – Soft-delete the member (like trainers). Mark `status = DISABLED` or `is_deleted = true`.

- **Memberships** (`MembershipViewSet`):
  - **POST** `/memberships/` – Create a membership record for a member. Body should include `member`, `start_date`, `end_date`, `plan` (optional), `amount_paid`, and `payment_mode`. The `member` must belong to this gym owner. This also implicitly activates the membership (set status ACTIVE).
    - _Behavior:_ After creation, the member has this membership until `end_date`. If desired, create an initial `Payment` in code or require the client to call the Payments API next.
  - **GET** `/memberships/?member=<member_uuid>` – List memberships, optionally filtered by `member`. A gym owner should only see their own members’ memberships.
  - **GET** `/memberships/{id}/` – Retrieve membership details.
  - **PUT** `/memberships/{id}/` – Update a membership. Allow extending the end date or updating amount/mode before it starts (but once active and in the past, it should normally not be edited). Do not allow changing the `member`.
  - **DELETE** `/memberships/{id}/` – Soft-delete/disable a membership (mark it expired).

- **Payments** (`PaymentViewSet`):
  - **POST** `/payments/` – Record a payment. Body includes `membership`, `amount`, `mode`. Gym owner links it to an existing membership.
  - **GET** `/payments/?member=<member_uuid>` – List payments, with optional filter by member (via membership→member). A gym owner sees only payments for their members.
  - **GET** `/payments/{id}/` – Get payment details.
  - **PUT** `/payments/{id}/` – Update a payment (e.g. correct an entry).
  - **DELETE** `/payments/{id}/` – Mark payment record as deleted/invalid.

> **Note:** The above endpoints should be placed under the accounts app. For example, register routers in `accounts/urls_users.py` (which is for Admin/GymOwner-managed routes). You can namespace them or prefix with `users/`, `memberships/`, and `payments/` as needed. Use `PermissionClasses = [IsAdminOrGymOwner]` on all these viewsets.

### 3.2 Trainer Endpoints

_Trainers (role=TRAINER) use these endpoints._ Protect them with `IsTrainer` permission. Endpoints:

- **Assigned Members** (`TrainerMemberViewSet`):
  - **GET** `/trainer/members/` – List members assigned to **this** trainer (`member.trainer = request.user`). Support search by name/phone as above. Only ACTIVE members.
  - **GET** `/trainer/members/{member_uuid}/` – Get details of one of the trainer’s members. Returns 404 if the member is not assigned to this trainer.
- **Note:** The `/trainer/` endpoints live in `accounts/urls_trainer.py` per the project structure.

> _Future placeholder:_ A trainer may later be able to assign workouts or notes to members (e.g. `POST /trainer/members/{id}/workouts/`), but **do not implement this in Phase 2** (it’s marked for Phase 3/4).

### 3.3 Member Endpoints

For Phase 2, members only use the `/auth/me/` endpoint (login and profile) which was implemented in Phase 1. Their workout logging is offline-only. No new member-specific REST API is needed in this phase.

## 4. Validation and Business Logic

- **Unique Fields:** Enforce `phone_number` uniqueness at the serializer/model level. Return 400 if a duplicate is attempted.
- **Required Fields:** On create, `phone_number`, `first_name`, and `password` must be provided for trainers/members. `start_date`, `end_date`, and `amount_paid` are required for memberships.
- **Membership Dates:** Validate that `start_date` ≤ `end_date`. After creation, membership automatically covers up to `end_date` (midnight). You may also enforce that new membership start after the last active membership end (no overlap).
- **Trainer Limits:** If `CustomUser.trainer_limit` > 0 for a gym owner, reject creating a new trainer when `Trainer.objects.filter(gym=self.user).count() >= trainer_limit`.
- **Access Control:** In each viewset’s `get_queryset()` method, filter results by `gym`. For example, `queryset = Trainer.objects.filter(gym=request.user)` for a gym owner, and `Trainer.objects.all()` for Admin. Similarly for members and memberships/payments. The `IsAdminOrGymOwner` permission should already restrict who can call the view; additional queryset filtering enforces object-level ownership.
- **Soft Deletes:** On "delete" actions, set `is_deleted = True` or `status = DISABLED` instead of hard deletion. The custom managers and default filters in Phase 1 should automatically exclude soft-deleted records from queries.

## 5. Serializers and View Details

- **Serializers:** Create separate serializers for each resource (Trainer, Member, Membership, Payment). In their `create()` methods, set `created_by = request.user` and in `update()`, set `updated_by = request.user`. Use `PasswordField(write_only=True)` for password inputs and call `user.set_password()` before saving. Ensure nested writes (e.g. assigning `trainer` by ID) are allowed.

- **Viewsets:** For each resource, use DRF’s `ModelViewSet` or `GenericViewSet + mixins` as appropriate. Example:

  ```python
  class TrainerViewSet(BaseModelViewSet):
      queryset = CustomUser.objects.filter(user_type='TRAINER', is_deleted=False)
      serializer_class = TrainerSerializer
      permission_classes = [IsAdminOrGymOwner]
      filter_backends = [DjangoFilterBackend, SearchFilter]
      search_fields = ['first_name','last_name','phone_number']
      def perform_create(self, serializer):
          serializer.save(created_by=self.request.user, gym=self.request.user, user_type='TRAINER')
  ```

  Similar pattern for `MemberViewSet`. Use `UserType` enums if defined. For Membership/Payment, use their serializers and set `created_by`. Use `PermissionClasses = [IsAdminOrGymOwner]`.

- **Routing:** Add routes in `accounts/urls_users.py` using `DefaultRouter` or manual `urlpatterns`. Example:

  ```python
  router = DefaultRouter()
  router.register('trainers', TrainerViewSet, basename='trainer')
  router.register('members', MemberViewSet, basename='member')
  router.register('memberships', MembershipViewSet)
  router.register('payments', PaymentViewSet)
  urlpatterns = router.urls
  ```

  Under `/trainer/` in `urls_trainer.py`, register `TrainerMemberViewSet` similarly.

- **PUT vs PATCH:** The user requested **full update (PUT)**. Ensure the client uses PUT for updates. DRF by default allows PATCH too, but you can choose to disallow partial updates or simply document that full data should be sent. Either is acceptable; PUT endpoints already exist if using ModelViewSet.

## 6. Media (Profile Pictures)

Profile pictures continue to use the `ImageField` on `CustomUser` (upload to `media/profile_pictures/`). The Django settings already configure `MEDIA_ROOT`. The serializers for Trainer/Member should accept an image file in multipart form data. For example, a `PUT /users/trainers/{id}/` request can include a new `profile_picture` file. The file should be saved to `media/`, and DRF will return the URL to the image in the response (as in Phase 1). No changes needed beyond normal DRF image handling.

## 7. API Examples

Below are sample request/response payloads illustrating the API design. (All responses are wrapped by the JSON envelope with `status` and `time`, not shown here.)

- **Create Trainer (Gym Owner role):**  
  **Request:** `POST /users/trainers/`

  ```json
  {
    "phone_number": "9876501234",
    "first_name": "Alice",
    "last_name": "Doe",
    "password": "TrainerPass123"
  }
  ```

  **Response (`201 Created`):**

  ```json
  {
    "data": {
      "uuid": "d3f1...e6a",
      "phone_number": "9876501234",
      "first_name": "Alice",
      "last_name": "Doe",
      "gender": null,
      "profile_picture": null,
      "status": "ACTIVE"
    },
    "message": "Trainer created successfully",
    "status": 201,
    "time": "2026-06-29T15:00:00Z"
  }
  ```

- **List Members (with search):** `GET /users/members/?search=John&page=1&page_size=20` returns an array of member objects.

- **Create Member with Membership:** Two-step approach:
  1. `POST /users/members/` with member info (like above, including an optional `"trainer": "<uuid>"`).
  2. `POST /memberships/` to assign membership:
     ```json
     {
       "member": "b7c2...f9d",
       "start_date": "2026-07-01",
       "end_date": "2026-07-31",
       "plan": "Monthly",
       "amount_paid": 1500.0,
       "payment_mode": "CASH"
     }
     ```
     Response will confirm membership creation.

- **Trainer Lists Assigned Members:** `GET /trainer/members/?search=Jane`  
  Only returns members where `member.trainer = (this trainer)` and `status=ACTIVE`.

- **Payment Recording:** `POST /payments/` with:
  ```json
  {
    "membership": "a5e2...c8d",
    "amount": 1500.0,
    "mode": "CASH"
  }
  ```
  This records a payment against that membership.

## 8. Migration Plan

To apply Phase 2 changes:

1. **Update Models:** Add `Membership` and `Payment` models to an appropriate app (e.g. create a new `memberships` app or add them in `accounts/models.py`). Update `CustomUser` model to add `trainer_limit = IntegerField(default=0)`.
2. **Makemigrations:** Run `python manage.py makemigrations` to generate migration files for the new models/fields.
3. **Migrate:** Run `python manage.py migrate` to apply changes to the MySQL database.
4. **Data Initialization (optional):** If existing members need a default membership record, add a migration or script to create one, but this is generally not needed for a fresh install.
5. **Update Codebase:** Add the new serializers, views, and URLs as described above. Follow the existing coding style (snake_case, descriptive names, logging if used).
6. **Check Permissions:** Ensure `settings.py` still points to `accounts.CustomUser` and the authentication backends for JWT remain in place.

## 9. Testing Checklist

Write unit tests (in `accounts/tests.py` or new test modules) covering:

- **Trainer API:**
  - Creating a trainer (valid and with duplicate phone).
  - Listing trainers (gym-owner sees only own trainers).
  - Retrieving a trainer (403/404 if cross-gym).
  - Updating a trainer (name change, disable).
  - Deleting a trainer (soft delete behavior).
  - Enforcing `trainer_limit` on create.
- **Member API:**
  - Creating a member (with and without assigning a trainer).
  - Listing members (search and pagination, filter by status).
  - Retrieving and updating member (reassign trainer, disable).
  - Deleting member (soft delete).
- **Membership API:**
  - Creating a membership (valid dates, overlapping scenario).
  - Retrieving/updating membership.
  - Ensuring only gym owner can manage their member’s memberships.
- **Payment API:**
  - Recording a payment (valid membership).
  - Retrieving/updating payment.
- **Trainer Endpoints:**
  - Listing assigned members (trainer sees only own members).
  - Access forbidden if trainer tries to access others.
- **Permissions:**
  - Verify `IsGymOwner` rejects non-gym-owners (e.g. another trainer user).
  - Verify `IsTrainer` rejects other roles.
- **Validation:**
  - Attempt invalid data (end_date before start_date, negative payment, etc.) and check for 400 responses.

All endpoints should return proper HTTP status codes (201, 200, 204, 400, 403, 404 as appropriate) and conform to the JSON envelope format. DRF’s test client and SimpleJWT testing should be used to simulate authenticated requests.

## 10. Coding Conventions

- Use existing **snake_case** style for variables and function names, **PascalCase** for class names.
- Follow the project’s import organization and ordering (e.g. Django imports first, then third-party, then local apps).
- Add relevant docstrings to new classes/methods describing purpose.
- Do not hard-code any values; use Django settings or constants for things like page size limits if already defined.
- Reuse validators from `core.validators` if possible (e.g. password strength).
- Register new models (`Membership`, `Payment`) in the Django admin (`accounts/admin.py`) for debugging convenience, but these admin changes are optional.

---

**In summary, Phase 2 adds gym-owner-managed CRUD for trainers, members, memberships, and payments, plus trainer endpoints to view assigned members.** Follow the Phase 1 architecture and style: use UUID keys, soft-delete logic, JWT auth, and the unified response format. This completes the core business workflows needed by the gym, paving the way for the workout and analytics features in Phase 3.
