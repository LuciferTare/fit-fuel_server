# 04_PHASE1_APIS_SERIALIZERS_VIEWSETS

> Fit&Fuel Backend – Phase 1 API, Serializer & ViewSet Specification

## Goal

Implement all REST APIs required for Phase 1 while following the existing backend project's architecture, naming conventions, base classes, response envelope, pagination, exception handling, and routing.

The AI agent MUST inspect the existing project before creating new ViewSets or serializers and extend existing abstractions wherever possible.

---

# API Principles

- Thin ViewSets.
- Business logic belongs in services if the project already uses them.
- Serializers handle validation.
- Models remain free of HTTP concerns.
- Every endpoint returns the common response envelope.
- List endpoints support `page` and `page_size`.

---

# Apps

accounts/
- models
- serializers
- views
- urls
- admin
- managers
- permissions (if project pattern exists)

---

# Endpoints

## Authentication

POST /auth/login

Serializer:
LoginSerializer

Fields:
- phone_number
- password

---

POST /auth/token/refresh

Serializer:
TokenRefreshSerializer

---

POST /auth/logout

Serializer:
LogoutSerializer

---

GET /auth/me

Returns authenticated user's profile.

---

POST /auth/change-password

Serializer:
ChangePasswordSerializer

Validation:
- old password correct
- new password strength
- new != old

---

# Gym Owner APIs

Accessible only to GYM_OWNER.

## Create Trainer

POST /users/trainers

Serializer:
TrainerCreateSerializer

Required:
- first_name
- last_name
- phone_number
- password
- date_of_birth
- gender
- profile_picture

Automatically assign:
- gym = request.user

Response:
Created trainer profile.

---

## List Trainers

GET /users/trainers

Return only trainers belonging to authenticated gym owner.

Supports:
page
page_size

Filters:
- status

Search:
- first_name
- last_name
- phone_number

---

## Retrieve Trainer

GET /users/trainers/{uuid}

Only same gym.

---

## Update Trainer

PUT/PATCH

Only same gym.

---

## Disable Trainer

PATCH

Status -> DISABLED

Never hard delete.

---

## Create Member

POST /users/members

Serializer:
MemberCreateSerializer

Same required fields as trainer.

gym assigned automatically.

trainer optional.

---

## List Members

GET /users/members

Supports:
page
page_size

Filters:
- trainer
- status
- gender

Search:
- first_name
- last_name
- phone_number

---

## Retrieve Member

GET /users/members/{uuid}

---

## Update Member

PUT/PATCH

---

## Disable Member

PATCH

Status -> DISABLED

---

## Assign Trainer

PATCH /users/members/{uuid}/assign-trainer

Body:

{
  "trainer_uuid":""
}

Validation:

Trainer belongs to same gym.

Member belongs to same gym.

One trainer only.

---

# Trainer APIs

GET /trainer/members

Returns only members assigned to authenticated trainer.

Supports pagination.

---

GET /trainer/members/{uuid}

Only assigned members.

---

# Member APIs

GET /member/profile

PATCH /member/profile

Members cannot edit:
- user_type
- gym
- trainer
- phone_number

Editable:
- first_name
- last_name
- profile_picture

DOB editing follows project policy.

---

# Serializer Rules

Never expose:
- password hash
- internal IDs

Expose UUIDs only.

Use nested serializers only where beneficial.

Validate:
- phone uniqueness
- gym ownership
- trainer ownership
- user status

---

# ViewSet Rules

Reuse project BaseViewSet if available.

Override:
- get_queryset()
- perform_create()
- perform_update()

Never duplicate ownership checks across methods.

---

# Permissions

Admin:
full access

Gym Owner:
own gym only

Trainer:
assigned members only

Member:
self only

Permission checks must exist at queryset level and serializer validation.

---

# Error Responses

400 Validation

401 Authentication

403 Authorization

404 Not Found

409 Duplicate phone

422 Business validation (if project standard supports it)

Use common response envelope.

---

# Pagination

Accept:
?page=1&page_size=20

Maximum page_size should follow existing project configuration.

---

# Testing Expectations

The implementation must include tests for:

- login
- logout
- refresh
- create trainer
- create member
- assign trainer
- unauthorized access
- cross-gym access denial
- phone uniqueness

---

# Explicitly Out of Scope

Workout APIs
Attendance
Measurements
Progress
Backup/Copy endpoints
Recipes
Music
Analytics
