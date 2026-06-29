# 03_PHASE1_AUTHENTICATION_JWT

> Fit&Fuel Backend – Phase 1 Authentication & JWT Specification

## Objective

Implement a production-ready authentication system using JWT for four user types:
- Platform Admin
- Gym Owner
- Trainer
- Member

Before implementation, inspect the existing backend project and reuse its authentication architecture, utilities, exception handling, response format, settings layout, and coding conventions.

---

# Authentication Principles

- Login is by **mobile number + password** only.
- No email authentication.
- No OTP.
- No forgot password flow in Phase 1.
- No email/mobile verification.
- JWT is stateless.
- Refresh token rotation must be enabled.
- Refresh token blacklist must be enabled.

---

# Token Configuration

Access Token Lifetime:
- 1 Day

Refresh Token Lifetime:
- 30 Days

Requirements:
- Rotate refresh token after every refresh.
- Blacklist old refresh token.
- Logout blacklists refresh token.

---

# Login Endpoint

POST /auth/login

Request

{
  "phone_number": "9876543210",
  "password": "********"
}

Validation:
- User exists
- Password correct
- Status == ACTIVE
- is_deleted == False

Return

{
  "status":200,
  "message":"Login successful",
  "data":{
      "access":"...",
      "refresh":"...",
      "user":{
          "uuid":"",
          "first_name":"",
          "last_name":"",
          "phone_number":"",
          "user_type":"",
          "status":"",
          "gym_id":"",
          "trainer_id":""
      }
  },
  "time":""
}

---

# Refresh Endpoint

POST /auth/token/refresh

Input:
{
 "refresh":"..."
}

Return:
New access token
New refresh token

Old refresh token must be blacklisted.

---

# Logout

POST /auth/logout

Input

{
 "refresh":"..."
}

Blacklist refresh token.

Return success.

---

# Authentication Backend

Use JWTAuthentication (or existing project implementation).

Populate request.user.

Never decode JWT manually in views.

---

# Authorization Rules

ADMIN
- Full system access.

GYM_OWNER
- Manage trainers.
- Manage members.
- View only own gym.

TRAINER
- View assigned members only.

MEMBER
- View/update only own profile.

---

# Password Rules

Minimum length: 8

Require:
- Uppercase
- Lowercase
- Number
- Special character

Hash using Django password hasher.

Never store plain passwords.

---

# User Creation

Admin creates Gym Owner.

Gym Owner creates Trainer.

Gym Owner creates Member.

Creator supplies initial password.

No registration endpoint for public users.

---

# Current User Endpoint

GET /auth/me

Return authenticated user profile.

---

# Change Password

POST /auth/change-password

Input:
old_password
new_password

Validate old password.

Hash new password.

---

# Authentication Errors

Invalid credentials -> 401

Disabled user -> 403

Deleted user -> 403

Suspended user -> 403

Invalid token -> 401

Expired token -> 401

All responses follow common response envelope.

---

# Security

- HTTPS only in production.
- Never log passwords.
- Never expose password hashes.
- Blacklist refresh tokens.
- Validate user status before issuing tokens.

---

# Django Admin

Admin login remains available.

Platform Admin managed via Django Admin and management command.

---

# Out of Scope

No backup APIs.
No workout authentication.
No sync logic.
No OTP.
No social login.
