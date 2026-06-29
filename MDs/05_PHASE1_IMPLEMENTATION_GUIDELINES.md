# 05_PHASE1_IMPLEMENTATION_GUIDELINES

> Fit&Fuel Backend – Phase 1 Implementation Guidelines

## Purpose

This document is the execution guide for the AI coding agent. It defines the order of implementation, coding standards, quality expectations, and acceptance criteria for Phase 1.

---

# 1. Analyze Before Coding

Before modifying the project, inspect:

- Project structure
- Installed applications
- Existing apps
- Base models
- Authentication classes
- Custom managers
- Serializers
- ViewSets
- Admin configuration
- Exception handlers
- Pagination
- Response wrappers
- URL routing
- Utility functions
- Logging
- Settings organization

Always extend existing architecture.

Never introduce duplicate implementations.

---

# 2. Implementation Order

Implement in the following sequence:

1. Configure AUTH_USER_MODEL
2. Create BaseModel integration
3. Create UserType/UserStatus enums
4. Implement custom User model
5. Register Django Admin
6. Configure JWT
7. Create serializers
8. Create authentication endpoints
9. Create Gym Owner APIs
10. Create Trainer APIs
11. Create Member APIs
12. Add pagination
13. Add tests
14. Verify migrations

Do not skip steps.

---

# 3. Coding Standards

- Follow PEP8.
- Use type hints where project style supports them.
- Keep ViewSets thin.
- Keep serializers focused on validation.
- Avoid duplicated business logic.
- Reuse helper methods.
- Write readable names.
- Do not hardcode configuration values.

---

# 4. Database Rules

- UUID primary keys.
- Soft delete only.
- Never hard delete users.
- Add indexes on searchable fields.
- Validate ownership at database/service layer.

---

# 5. Security

- Hash passwords with Django hasher.
- Never expose password hashes.
- Validate JWT on every protected endpoint.
- Blacklist refresh tokens on logout.
- Reject disabled, suspended and deleted users.

---

# 6. API Rules

Every response follows:

{
  "status": 200,
  "message": "",
  "data": {},
  "time": ""
}

All list APIs support:

- page
- page_size

---

# 7. Validation Checklist

Trainer:
- belongs to gym

Member:
- belongs to gym

Assignment:
- trainer and member belong to same gym

Phone:
- unique

UserType:
- immutable after creation unless performed by Admin

---

# 8. Django Admin

Admin must support:

- searching
- filtering
- ordering
- profile picture preview if project convention exists
- status management

---

# 9. Testing Checklist

Authentication:
- login
- logout
- refresh
- invalid credentials
- disabled user
- suspended user

Authorization:
- gym isolation
- trainer isolation
- member self-access

CRUD:
- trainer creation
- member creation
- trainer assignment
- updates
- soft delete

---

# 10. Migration Checklist

- makemigrations
- migrate
- verify AUTH_USER_MODEL
- verify admin
- verify JWT
- verify media uploads

---

# 11. Acceptance Criteria

Phase 1 is complete only when:

✓ Platform Admin can create Gym Owners.

✓ Gym Owners can create Trainers.

✓ Gym Owners can create Members.

✓ Trainers can access only assigned members.

✓ Members can access only their own profile.

✓ JWT authentication works.

✓ Refresh token rotation works.

✓ Refresh blacklist works.

✓ Django Admin works.

✓ Soft delete works.

✓ UUIDs are used.

✓ Pagination works.

✓ API responses follow common envelope.

---

# 12. Explicit Non-Goals

Do not implement:

- Workout storage
- Workout backup/copy
- Attendance
- Membership plans
- Payments
- WhatsApp
- Notifications
- Analytics
- Recipes
- Music
- Exercise APIs

These belong to future phases.

---

# 13. Future Compatibility

Design Phase 1 so later phases can introduce:

- Backup engine
- Workout replication
- Attendance
- Progress analytics
- Membership management
- Subscription billing
- WhatsApp automation
- Trainer notes
- Diet plans

without breaking existing APIs or models.

End of Phase 1.
