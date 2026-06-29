# 01_PHASE1_PROJECT_ARCHITECTURE

> Fit&Fuel Backend – Phase 1 Architecture Specification

## Purpose
This document defines the architectural rules for Phase 1.

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

## Stack
- Python 3.x
- Django 5.2.4
- Django REST Framework 3.16.0
- MySQL (mysqlclient 2.2.7)
- UUID primary keys
- JWT Authentication
- Local MEDIA storage

## Scope
Implement only:
- Custom User
- JWT Authentication
- User Roles
- Gym hierarchy
- Trainer assignment
- Profile APIs
- Django Admin

Do NOT implement workouts, attendance, analytics, sync, nutrition or music.

## Hierarchy

Platform Admin
└── Gym Owner
    ├── Trainer
    └── Member

Rules:
- Only Admin creates Gym Owners.
- Gym Owners create Trainers and Members.
- Trainers cannot create users.
- Members cannot create users.
- One Trainer belongs to one Gym Owner.
- One Member belongs to one Gym Owner.
- One Trainer supervises many Members.
- One Member can have only one Trainer.

## Gym Representation

No Gym model in Phase 1.

gym_id references the UUID of the Gym Owner.

## BaseModel

All models inherit:
- uuid
- created_at
- updated_at
- created_by
- updated_by
- is_deleted
- deleted_at

Soft delete only.

## UserStatus

Implement:
- ACTIVE
- DISABLED
- SUSPENDED
- DELETED

## JWT

Access Token: 1 day

Refresh Token: 30 days

Refresh rotation enabled.

Refresh blacklist enabled.

Logout blacklists refresh token.

## API Response

{
  "status": 200,
  "message": "",
  "data": {},
  "time": ""
}

## Pagination

Support:
- page
- page_size

## Media

Store profile pictures in MEDIA_ROOT.

## Coding Rules

- Keep business logic outside views.
- Register all models in Django Admin.
- Follow project naming conventions.
- Reuse existing utilities.
- Add migrations.
- Write maintainable code.

## Deliverables

- Custom User
- Authentication
- JWT
- User hierarchy
- Profile management
- Django Admin integration
- Production-ready Phase 1 foundation
