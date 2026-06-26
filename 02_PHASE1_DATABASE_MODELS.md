# 02_PHASE1_DATABASE_MODELS

> Fit&Fuel Backend – Phase 1 Database Models Specification

## Objective

Implement the complete database foundation for Phase 1.

Before creating any model, inspect the existing backend project and reuse:
- BaseModel
- Managers
- Mixins
- Naming conventions
- App structure
- UUID implementation
- Soft-delete implementation
- Admin registration style

Do not introduce a parallel architecture.

---

# Database Principles

- Every model uses UUID primary keys.
- Every model inherits BaseModel.
- Never hard delete business data.
- Use ForeignKey relationships with explicit related_name.
- Add db_index on frequently queried fields.
- Add verbose_name and verbose_name_plural where project style uses them.

---

# Enums

## UserType

- ADMIN
- GYM_OWNER
- TRAINER
- MEMBER

## UserStatus

- ACTIVE
- DISABLED
- SUSPENDED
- DELETED

---

# Custom User Model

Extend AbstractBaseUser + PermissionsMixin (or existing project standard).

Authentication identifier:
- phone_number (unique)

Fields:

Identity
- uuid
- phone_number (unique)
- password

Profile
- first_name
- last_name
- date_of_birth
- age (computed property, not persisted unless project requires)
- gender
- profile_picture

Business
- user_type
- status

Relationships
- gym (FK -> User, nullable, limit to GYM_OWNER)
- trainer (FK -> User, nullable, limit to TRAINER)

Audit
- created_by
- updated_by
- created_at
- updated_at
- is_deleted
- deleted_at

Django
- is_staff
- is_superuser
- is_active
- last_login

Notes:
- Gym Owner has gym = NULL.
- Trainer.gym points to Gym Owner.
- Member.gym points to Gym Owner.
- Member.trainer is optional.

---

# Constraints

Phone number unique.

Only one trainer per member.

Trainer and gym must belong together.

Trainer must belong to same gym as member.

Admin cannot have gym.

Gym Owner cannot have trainer.

Trainer cannot reference another trainer.

---

# Database Validation

Enforce through:
- model.clean()
- serializer validation
- service layer

Do not rely only on frontend.

---

# Indexes

Create indexes for:

phone_number
user_type
status
gym
trainer
created_at

---

# Managers

Provide:

objects
active_objects (exclude deleted)

If project already provides soft-delete manager, reuse it.

---

# Admin

Register User model.

List:
- phone
- first_name
- last_name
- user_type
- status
- gym
- trainer

Search:
- phone
- first_name
- last_name

Filters:
- user_type
- status

---

# Relationships

Admin
  └─ GymOwner
        ├─ Trainer
        │      └─ Members
        └─ Members

Member assignment optional.

---

# Migration Requirements

Initial migration must:

Create enums.
Create custom user.
Configure AUTH_USER_MODEL.
Register admin.

No workout tables.

---

# Out of Scope

Do not create:

WorkoutSession
Exercise
ExerciseSet
Measurements
Attendance
Membership
Diet
Recipe
Music

These belong to later phases.
