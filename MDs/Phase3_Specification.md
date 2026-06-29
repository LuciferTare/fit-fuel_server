# Phase 3 Backend Design Specification – Fit&Fuel

**Executive Summary:** Phase 3 turns the backend into an *offline-first* “cloud backup” service without yet implementing detailed workout models. We will add attendance tracking, membership payments, trainer capacity limits, notification hooks, and reporting endpoints, while providing generic sync/upload endpoints for client data. The backend remains secondary to the app’s local SQLite database: it only stores and serves copies of data (point-in-time backups) to enable cross-user collaboration. We will follow the existing Django/DRF project conventions (apps, naming, base models, JSON response format) and use UUIDs and audit fields everywhere. Authentication remains JWT-based with 1-day access tokens and 30-day refresh tokens (blacklisted on logout). We will *not* delete users or history; soft-deletion and status flags handle removals. Below is a detailed breakdown of models, APIs, sync logic, and related concerns.

## 1. Project Structure and Style

- **Analyze existing code first:** The AI agent should scan the repository to understand app layouts, naming patterns (e.g. `apps.accounts`, `apps.common`), serializer conventions, and error handling. Follow any existing base `BaseModel`, exception types, and utilities.
- **Apps:** Create or extend apps as follows:
  - `accounts` (or similar): extend the CustomUser model if needed (e.g. add `max_trainers` for owners).
  - `gyms` (or `members`/`trainers`): models for assignments, payments, and capacity.
  - `attendance`: attendance model and views.
  - `payments`: member payments.
  - `notifications`: stub services for SMS/WhatsApp.
  - `reports`: reporting endpoints.
  - `sync` or `backup`: endpoints for uploading/downloading client changes.
  - `common`: shared BaseModel, pagination, permissions, etc.
- **Coding Style:** Use Django 5.2.4 and DRF 3.16.0 idioms. Stick to snake_case for fields and urls, restful viewsets or CBVs, explicit `@action` for custom actions. Use standard JSON response format (`{"status":<code>,"message":...,"data":...,"time":...}`) as in Phase 1. Follow any existing indentation, docstring, and naming style. Include doctrings on new classes/methods.
- **BaseModel:** All models inherit `BaseModel` with at least: 
  ```python
  class BaseModel(models.Model):
      uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)
      created_by = models.UUIDField(null=True)   # user UUID
      updated_by = models.UUIDField(null=True)
      is_deleted = models.BooleanField(default=False)
      deleted_at = models.DateTimeField(null=True)
      class Meta: abstract = True
  ```
  (Assuming Phase 1 defined something similar.) All foreign keys should use `on_delete=models.PROTECT` or `CASCADE` as appropriate, and be indexed. 

## 2. Data Models

We will add the following models and fields (UUID primary keys throughout):

- **CustomUser (extend existing):** Add fields for GymOwner capacity and member fields:
  - `max_trainers`: `PositiveIntegerField(default=0)` (applicable only if `usertype=GymOwner`; max allowed trainers).
  - If not already present, ensure `gym_id` field (UUID of GymOwner) and `trainer` field (UUID of assigned trainer) exist on members/trainers as per Phase 2.
  - *Note:* The user’s gym is implicitly the GymOwner user referenced by `gym_id`. No separate Gym model is added. 

- **TrainerAssignment (new):** Even though Phase 2 attached `trainer` FK to User, to track history we may add:
  ```python
  class TrainerAssignment(BaseModel):
      trainer = models.ForeignKey(CustomUser, on_delete=models.PROTECT, limit_choices_to={'usertype':'Trainer'})
      member  = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='trainer_assignments')
      assigned_by = models.UUIDField()  # GymOwner UUID
      assigned_at = models.DateTimeField(auto_now_add=True)
      is_active = models.BooleanField(default=True)
  ```
  This allows reassignments without losing history (setting old `is_active=False` and creating a new record). However, if this is too heavy, one could simply update the `trainer` field on the `CustomUser` Member record. Either approach is acceptable; if no history needed, updating Member’s `trainer` directly is simpler.

- **Attendance (new):** Tracks member check-ins/outs. Fields:
  ```python
  class Attendance(BaseModel):
      member   = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'usertype':'Member'})
      check_in = models.DateTimeField()
      check_out = models.DateTimeField(null=True, blank=True)
      check_in_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
      check_in_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
      check_out_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
      check_out_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
  ```
  - Optionally, store `location_name` or `address` if reverse geocoding. GPS fields give check-in/out location.

- **Payment (new):** Records membership fee payments by members:
  ```python
  class Payment(BaseModel):
      member = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'usertype':'Member'})
      amount = models.DecimalField(max_digits=10, decimal_places=2)
      date = models.DateField()  # date of payment
      mode = models.CharField(max_length=20, choices=[('Cash','Cash'),('Online','Online')])
      created_by = models.UUIDField()  # GymOwner UUID who recorded it
  ```
  - On creating a Payment, the GymOwner also sets or updates that Member’s membership start/end dates (stored as fields on `CustomUser`, see below).

- **Membership Fields (new on CustomUser):** Instead of a separate model, add to `CustomUser` (usertype=Member):
  - `membership_start = DateField(null=True)`
  - `membership_end = DateField(null=True)`
  - `membership_status = CharField(choices=[('Active','Active'),('Expired','Expired')])`
  - Optionally a `membership_plan = CharField(choices=[('Monthly','Monthly'),('Quarterly','Quarterly'),...])` if needed for reports.

- **Trainer Capacity:** No separate model. We will use `CustomUser.max_trainers`. Also track `current_trainer_count = customUser.customuser_set.filter(usertype='Trainer').count()`. Add validation in the Trainer-creation API to enforce `current < max_trainers`. No need to store count in DB (can compute on the fly).

- **Sync Metadata (new on all client-backed tables):** To prepare for sync, ensure each table has:
  - `sync_status` (e.g. choices: `PENDING`, `SYNCED`, `MODIFIED`, `DELETED`),
  - `version` or `client_timestamp` to detect conflicts.
  If not already present, add these to local models. On the server side, `updated_at` can serve for LWW conflicts. We may skip explicit `version`; rely on `updated_at` or a `version = IntegerField` (auto-incremented each change).
  
*(No workout/exercise/metrics models are added yet; that is Phase 4.)*

## 3. Authentication & Permissions

- **Roles:** As before: `Admin (Platform)`, `GymOwner`, `Trainer`, `Member`. Platform Admin (us) creates GymOwner accounts. GymOwner (single per gym) can create Trainers and Members for their gym. Trainers manage only their assigned Members. Members have no server APIs (all offline usage).
- **JWT Tokens:** Use the same SimpleJWT setup (access 1 day, refresh 30 days). On logout, the refresh token is blacklisted (via `rest_framework_simplejwt.token_blacklist`) to prevent reuse.
- **Permission checks:** Enforce role-based access in all viewsets. e.g. 
  - Only **GymOwner** can create/update Trainers and Members of their own gym (`gym_id=owner`).
  - **Trainer** can list/view *assigned* Members only (`CustomUser.objects.filter(trainer=request.user)`).
  - **Member** has no server endpoints besides possibly triggering sync.
  - **Admin** can do anything (if an admin panel exists, else Admin is platform-only for owner creation).
- **Object-level filtering:** Implicit in permission logic (e.g. querysets filter by `gym_id=request.user.gym_id` or `trainer=request.user.id`).
- **Audit fields:** In each create/update, set `created_by`/`updated_by` to the user’s UUID from the JWT.

## 4. Offline-First Sync Endpoints

We treat the server as a *backup* of local data. We add generic endpoints for clients to push and fetch changes:

- **POST `/api/backup/upload/`:** Accepts a payload of changed records from the client. For example:
  ```json
  {
    "user_id": "<member uuid>",
    "changes": [
        {"model": "attendance.Attendance", "data": {...}, "action": "create"},
        {"model": "attendance.Attendance", "data": {...}, "action": "update"},
        {"model": "attendance.Attendance", "data": {"uuid": "...", "is_deleted": true}, "action": "delete"},
        // ... other models like Workout (future) ...
    ]
  }
  ```
  For each change:
  - On `create`/`update`, server will insert or update the record (identifying by UUID). Compare timestamps (`updated_at`) for conflicts; use **Last-Write-Wins**: newer record (server or client) wins.
  - On `delete`, mark `is_deleted=True` on server.
  - Respond with `204 No Content` or a summary (depending on design). Errors cause a `409 Conflict` or `422 Unprocessable` if relational constraints fail.
  - This endpoint requires authentication (GymOwner or Trainer pushing member changes, or Admin). Members generally won’t call this (they are offline).
  
- **GET `/api/backup/download/`:** (Optional in Phase 3.) Client may call this with last sync timestamp to fetch any new updates. For example:
  ```
  GET /api/backup/download/?user_id=<uuid>&since=2026-06-20T00:00:00Z
  ```
  Server returns changed objects (e.g. if Trainer assigned a workout or notes) to clients. For now, likely empty since no server-managed data for members exists yet.

- **Sync processing:**  
  - Maintain a *Change Queue* on client. Clients should batch-create JSON payloads of all local changes since last sync.  
  - On upload, the server updates its DB.  
  - On conflict (e.g. client and server modified same field), use LWW (compare `updated_at`). The Android documentation notes LWW is common for mobile apps.  
  - The backend should **never overwrite a member’s local workout history** without latest timestamp; this is backup-only.  
  - No two clients (members) will edit the *same* member record, since each member is one person. The only multi-user conflicts might be between trainer and member updating a member record offline concurrently (unlikely with current offline use-case). 

## 5. Attendance APIs

Enable GymOwner and Trainer to record member attendance. (Members do check-in on app, but GymOwner/Reception may also log it.)

- **POST `/api/attendance/checkin/`**: JSON body: `{"member_id": "<uuid>", "timestamp": "2026-06-29T08:00:00Z", "lat": 19.2183, "lng": 72.9781}`. Creates an Attendance record with `check_in` and location. Must be GymOwner or Trainer, and member must belong to same gym (or assigned to trainer). Responds with created record ID.

  Example **cURL**:
  ```bash
  curl -X POST /api/attendance/checkin/ \
       -H "Authorization: Bearer <token>" \
       -H "Content-Type: application/json" \
       -d '{"member_id":"abc123...","timestamp":"2026-06-29T08:00:00Z","lat":19.18,"lng":72.97}'
  ```
  Example response:
  ```json
  {
    "status": 201,
    "message": "Checked in successfully.",
    "data": {"uuid":"550e8400-e29b-41d4-a716-446655440000","member":"abc123...", "check_in":"2026-06-29T08:00:00Z", ...},
    "time": "2026-06-29T08:00:00Z"
  }
  ```

- **POST `/api/attendance/checkout/`**: JSON body: `{"attendance_id": "<uuid>", "timestamp":"2026-06-29T10:00:00Z", "lat":..., "lng":...}`. Marks check-out for an existing attendance record. Sets `check_out` and location. Returns updated record.

- **GET `/api/attendance/?member_id=...&date=...`**: (Optional) Fetch attendance records for a member (for reports/UI). Paginates if needed.

_Add indexes on `Attendance.member_id` and maybe on (`member_id`, `check_in`) to speed queries._ ForeignKey auto-indexes, but additional composite indexes can help weekly queries.

## 6. Membership Payments & Subscription

- **Payment Model:** As defined above, tracks member payments. GymOwner creates this.

- **POST `/api/payments/`**: Create a Payment. JSON: 
  ```json
  {
    "member_id": "abc123...",
    "date": "2026-06-01",
    "amount": "1500.00",
    "mode": "Cash",
    "start_date": "2026-06-01",
    "end_date": "2026-06-30"
  }
  ```
  The server should:
  1. Create a Payment record.
  2. Update the Member’s `membership_start` and `membership_end` fields to the provided dates.
  3. Set `membership_status="Active"` (until end date passes).
  4. Respond with payment details.

  Example **cURL**:
  ```bash
  curl -X POST /api/payments/ \
       -H "Authorization: Bearer <token>" \
       -H "Content-Type: application/json" \
       -d '{"member_id":"abc123...","date":"2026-06-01","amount":"1500.00","mode":"Cash","start_date":"2026-06-01","end_date":"2026-06-30"}'
  ```
  Example response:
  ```json
  {
    "status": 201,
    "message": "Payment recorded and membership updated.",
    "data": {"uuid":"550e8400-e29b-41d4-a716-446655440111","member":"abc123...","amount":"1500.00","date":"2026-06-01","mode":"Cash"},
    "time": "2026-06-29T09:00:00Z"
  }
  ```

- **GET `/api/payments/?member_id=...`**: List payments for a member (paginated). Supports query by `member_id`.

- **Membership Plans (front-end):** GymOwner UI might present plan options (monthly, etc.), but backend only cares about actual dates. Do *not* enforce fixed durations – just store whatever dates the owner provides.

- **Indexes:** Add an index on `Payment.member_id` (default) and possibly on `date` for queries.

## 7. Trainer Capacity Enforcement

- **GymOwner Limits:** When creating Trainers:
  - Before `POST /api/trainers/`, count existing trainers for this gym (`CustomUser.objects.filter(gym_id=request.user.id, usertype='Trainer').count()`). Compare to `max_trainers`. If count ≥ max, reject with 400 and message.
  - GymOwner can update `max_trainers` via their profile endpoint if needed (optional).

- **Tracking Current Count:** We do not store it separately (it can be computed). Ensure an index on `CustomUser.gym_id` and `CustomUser.usertype` to speed counts/queries.

## 8. Notification (WhatsApp/SMS) Hooks

We will define placeholders/hooks; actual sending is out-of-scope for now:

- **Trigger Points (internal):**
  - *Consecutive absence:* A scheduled check (e.g. daily management command) that finds Members who have no `Attendance` in >N days. For each, create a notification task (not implemented fully).
  - *Membership near expiration:* Similarly, find `CustomUser` members whose `membership_end` is within X days or passed, to remind renewal.

- **Services:**
  - Create a `notifications/` app or module with utility functions:
    ```python
    def send_sms(phone_number: str, message: str):
        # Placeholder: integrate with Twilio or other SMS API.
        pass

    def send_whatsapp(phone_number: str, template_name: str, params: dict):
        # Placeholder for Twilio WhatsApp API.
        pass
    ```
    (Document these as stubs to be implemented with an actual provider.)
  - No endpoints for sending (we assume server-initiated or via management commands). 

- **Webhook Placeholders:** Define `Notification` model if desired to log sent messages (optional). If not, at least log to console or file.

- **Citing Example:** Twilio’s Python API uses `Client.messages.create(from_, body, to)` for SMS/WhatsApp. We won’t implement it now, but note it for future.

## 9. Reporting Endpoints

Provide summary reports for gym owners:

- **GET `/api/reports/inactive-members/?days=N`**: List members with no attendance in the last N days. E.g. `?days=7`. Compute via: Members of this gym whose last `Attendance.check_in` is older than N days (or null). Return array of members (id, name, days_inactive).
  ```json
  {
    "status": 200,
    "message": "Success",
    "data": [
      {"member_id":"m1","name":"Alice","last_visit":"2026-06-15","days_inactive":14},
      {"member_id":"m2","name":"Bob","last_visit":null,"days_inactive":30},
      ...
    ],
    "time":"2026-06-29T10:00:00Z"
  }
  ```

- **GET `/api/reports/trainer-workload/`**: For each trainer in the gym, report number of active members assigned (and optionally, average sessions per week if workouts existed). Returns:
  ```json
  {
    "status": 200,
    "message": "Success",
    "data": [
      {"trainer_id":"t1","name":"TrainerA","member_count":12},
      {"trainer_id":"t2","name":"TrainerB","member_count":8},
      ...
    ],
    "time":"2026-06-29T10:05:00Z"
  }
  ```

- **GET `/api/reports/membership-expiry/?days=X`**: List members whose `membership_end` is within the next X days or already expired within X days. E.g. `?days=7`. For renewal reminders.
  ```json
  {
    "status": 200,
    "message": "Success",
    "data": [
      {"member_id":"m1","name":"Charlie","expiry_date":"2026-07-01","days_left":2},
      ...
    ],
    "time":"2026-06-29T10:10:00Z"
  }
  ```

(Endpoints should be `GET`, require GymOwner auth. Use pagination where result sets may be large. We can filter by date range etc. These are read-only summary views.)

## 10. Database Indexing & Aiven MySQL Considerations

- **Indexes:**  
  - All foreign keys have implicit indexes. Add explicit indexes on frequently queried fields:
    - `Attendance(member_id, check_in)` composite for inactivity queries.
    - `Payment(member_id, date)`.
    - `CustomUser(gym_id, usertype)` for trainer/member queries.
  - For reports, index `membership_end`.
- **Aiven (MySQL) Backup:** Aiven automatically performs daily full backups and continuous binlogs for point-in-time recovery. We do not need to manage backups manually. Note: during a backup, DDL like `ALTER TABLE` may wait on a “backup lock”. Schedule migrations or heavy DDL outside backup windows.
- **Performance:** Given likely moderate data volume, the main considerations are indexing as above. We rely on InnoDB’s foreign key integrity. As a StackOverflow answer notes, foreign keys carry a minor write overhead but ensure consistency and can improve select performance (the auto-created index is used). The trade-off is acceptable for data integrity.
- **Failover/HA:** (Beyond Phase 3) but Aiven provides high availability options. For now, just ensure the Django DB connection uses Aiven credentials and handle transient errors by retrying.
- **Connection:** Use `mysqlclient` 2.2.7 as given. Set `CONN_MAX_AGE` to a reasonable value (e.g. 60s) for persistent connections. Use Django’s connection pooling if available.

## 11. Migrations

All model changes require migrations. Example steps:

- **CustomUser changes:** Add fields (`membership_start`, `membership_end`, `membership_status`, `max_trainers`). These are new columns; use `null=True` for backward compatibility. Create a migration.
- **Create Attendance and Payment tables:** New models => migrations.
- **TrainerAssignment (if used):** New table.
- **Sync metadata (if any):** Add fields to relevant tables.
- **Indexes:** You can add migrations for composite indexes, e.g.:
  ```python
  migrations.AddIndex(
      model_name='attendance',
      index=models.Index(fields=['member','check_in'], name='attendance_member_check_in_idx')
  )
  ```
- **Sample SQL for indexes:** 
  ```sql
  ALTER TABLE attendance ADD INDEX idx_attendance_member_checkin (member_id, check_in);
  ALTER TABLE payments ADD INDEX idx_payments_member_date (member_id, date);
  ALTER TABLE customuser ADD INDEX idx_customuser_gym_type (gym_id, usertype);
  ```
- **Foreign Keys:** Already created via models. We should use `CASCADE` or `PROTECT` as needed.
- **Data migration:** None needed (all new data). If changing any existing logic (e.g. how membership is determined), be careful.
- **Deletion:** Mark `is_deleted=True` instead of actual DROP.

_Reminder:_ Review the **Aiven backup docs** before any destructive migration: avoid DDL during backup if possible. Possibly disable or schedule downtime.

## 12. Sample API Usage (Requests/Responses)

Below are examples for key endpoints. All responses follow the `{status,message,data,time}` format.

### Attendance Check-In
```bash
curl -X POST https://api.fitfuel.com/api/attendance/checkin/ \
     -H "Authorization: Bearer <access_token>" \
     -H "Content-Type: application/json" \
     -d '{
           "member_id": "550e8400-e29b-41d4-a716-446655440000",
           "timestamp": "2026-06-29T08:00:00Z",
           "lat": 19.2183,
           "lng": 72.9781
         }'
```
**Response (201 Created):**
```json
{
  "status": 201,
  "message": "Member checked in.",
  "data": {
    "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "member_id": "550e8400-e29b-41d4-a716-446655440000",
    "check_in": "2026-06-29T08:00:00Z",
    "check_out": null,
    "check_in_lat": "19.218300",
    "check_in_lng": "72.978100",
    "check_out_lat": null,
    "check_out_lng": null
  },
  "time": "2026-06-29T08:00:00Z"
}
```

### Attendance Check-Out
```bash
curl -X POST https://api.fitfuel.com/api/attendance/checkout/ \
     -H "Authorization: Bearer <access_token>" \
     -H "Content-Type: application/json" \
     -d '{
           "attendance_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
           "timestamp": "2026-06-29T10:15:00Z",
           "lat": 19.2190,
           "lng": 72.9790
         }'
```
**Response:**
```json
{
  "status": 200,
  "message": "Member checked out.",
  "data": {
    "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "member_id": "550e8400-e29b-41d4-a716-446655440000",
    "check_in": "2026-06-29T08:00:00Z",
    "check_out": "2026-06-29T10:15:00Z",
    "check_in_lat": "19.218300",
    "check_in_lng": "72.978100",
    "check_out_lat": "19.219000",
    "check_out_lng": "72.979000"
  },
  "time": "2026-06-29T10:15:00Z"
}
```

### Record a Membership Payment
```bash
curl -X POST https://api.fitfuel.com/api/payments/ \
     -H "Authorization: Bearer <access_token>" \
     -H "Content-Type: application/json" \
     -d '{
           "member_id": "550e8400-e29b-41d4-a716-446655440000",
           "date": "2026-06-01",
           "amount": "1500.00",
           "mode": "Cash",
           "start_date": "2026-06-01",
           "end_date": "2026-06-30"
         }'
```
**Response (201 Created):**
```json
{
  "status": 201,
  "message": "Payment recorded and membership updated.",
  "data": {
    "uuid": "a987fcd0-32ba-4100-af09-1a2b3c4d5e6f",
    "member_id": "550e8400-e29b-41d4-a716-446655440000",
    "amount": "1500.00",
    "date": "2026-06-01",
    "mode": "Cash"
  },
  "time": "2026-06-29T09:00:00Z"
}
```

### Fetch Inactive Members Report
```bash
curl https://api.fitfuel.com/api/reports/inactive-members/?days=14 \
     -H "Authorization: Bearer <access_token>"
```
**Response (200 OK):**
```json
{
  "status": 200,
  "message": "Success",
  "data": [
    {"member_id":"550e8400-e29b-41d4-a716-446655440001","name":"Alice","last_visit":"2026-06-10","days_inactive":19},
    {"member_id":"550e8400-e29b-41d4-a716-446655440002","name":"Bob","last_visit":null,"days_inactive":30}
  ],
  "time":"2026-06-29T11:00:00Z"
}
```

### Trainer Workload
```bash
curl https://api.fitfuel.com/api/reports/trainer-workload/ \
     -H "Authorization: Bearer <access_token>"
```
**Response:**
```json
{
  "status": 200,
  "message": "Success",
  "data": [
    {"trainer_id":"550e8400-e29b-41d4-a716-446655441000","name":"Trainer One","member_count":12},
    {"trainer_id":"550e8400-e29b-41d4-a716-446655441001","name":"Trainer Two","member_count":8}
  ],
  "time":"2026-06-29T11:05:00Z"
}
```

### Membership Expiry
```bash
curl https://api.fitfuel.com/api/reports/membership-expiry/?days=7 \
     -H "Authorization: Bearer <access_token>"
```
**Response:**
```json
{
  "status": 200,
  "message": "Success",
  "data": [
    {"member_id":"550e8400-e29b-41d4-a716-446655440003","name":"Charlie","expiry_date":"2026-07-01","days_left":2}
  ],
  "time":"2026-06-29T11:10:00Z"
}
```

## 13. Deployment & Testing

- **Migrations:** After code is generated, run `python manage.py makemigrations` then `migrate` on the Aiven MySQL database. Monitor for migration warnings (especially the lock warning in Aiven docs). Schedule at low-usage time.
- **Linters/Formatters:** Run `flake8` and `black` (or `isort`) on all changed files. Example: `flake8 apps/ attendance/models.py`, `black --check .`.
- **Tests:** Add comprehensive tests. Use DRF’s `APITestCase`. Key tests:
  - Attendance: creating check-in/out updates records correctly, unauthorized roles are blocked.
  - Payments: posting valid data updates membership fields; invalid data returns errors.
  - Capacity: cannot create beyond `max_trainers`; allowed below limit.
  - Reports: computed fields (days_inactive, etc.) are correct.
  - Sync: simulate `POST /backup/upload/` with create/update/delete records, verify server data.
  - Auth: JWT login, access control, blacklist on logout. Use DRF’s SimpleJWT test utilities.
- **Run Test Suite:** `python manage.py test`. Ensure coverage for new endpoints.
- **Logging:** Ensure errors are logged (Django default) and sensitive info is not in logs.

## 14. Implementation Checklist (Phase 3)

**User Stories & Story Points:**

1. **Attendance Tracking (5 pts):**  
   - Model + migrations, serializers, views for check-in/out.  
   - Permissions and tests.  

2. **Payment & Membership (4 pts):**  
   - Payment model, API to record payment and update membership dates.  
   - Tests: payment creation, membership field updates.  

3. **Reports (3 pts):**  
   - Endpoints for inactive-members, trainer-workload, membership-expiry.  
   - Aggregate queries and pagination.  

4. **Trainer Capacity (2 pts):**  
   - Add `max_trainers` field, enforce in trainer creation.  
   - Validation and error handling.  

5. **Sync/Backup Endpoints (5 pts):**  
   - Implement generic `/backup/upload/` and `/backup/download/`.  
   - Change-queue payload processing, LWW conflict logic.  

6. **Notification Hooks (2 pts):**  
   - Add placeholder functions `send_sms` / `send_whatsapp` and outline triggers.  
   - (No actual integration coding, just structure.)  

7. **Database Indexes (1 pt):**  
   - Add necessary indexes via migrations (attendance, payments, user).  
   - Document SQL if needed.  

8. **Testing (3 pts):**  
   - Write unit/feature tests for above.  
   - Ensure all pass.  

9. **Deployment Prep (2 pts):**  
   - Write migration and deployment instructions (Aiven settings, cron for `flushexpiredtokens`).  
   - Monitor backup configuration.  

_Total: ~27 points._ Adjust based on team sizing.

## References

- *Django REST Framework Pagination:* Use `PageNumberPagination` with `page` and `page_size` params for all list endpoints.  
- *JWT Blacklist:* Use SimpleJWT’s blacklist app to revoke refresh tokens on logout.  
- *Offline Sync Strategy:* A “last write wins” approach is common for mobile clients. Timestamp-based LWW is simple but must be documented.  
- *Aiven MySQL Backups:* Aiven auto-takes daily encrypted backups and binlogs for PITR. Avoid DDL during backups (or accept the brief lock).  
- *Indexing:* Foreign keys auto-create indexes. Adding FKs gives data integrity, with only minor write overhead; add additional composite indexes as needed.  

Be sure to **follow existing code conventions**. After implementing, run all existing tests to ensure nothing broke. This spec should guide the AI coder to expand the backend while preserving style and ensuring an offline-capable architecture.