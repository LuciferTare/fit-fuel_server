# Django Backend Starter

A production-ready Django REST Framework boilerplate with JWT authentication, email verification, geolocation, and a standardized API response format.

---

## Features

- **JWT Authentication** — access + refresh tokens with rotation and blacklisting
- **Email verification** — token-based activation on registration
- **Custom User model** — email as primary identifier, extensible
- **Standardized API responses** — unified JSON envelope via custom renderer
- **OpenAPI / Swagger docs** — auto-generated at `/docs/`
- **GeoIP2 + User-Agent** — IP location and device detection endpoint
- **CORS enabled** — ready for cross-origin frontends
- **Multi-level logging** — console + rotating log files
- **MySQL** — configured via environment variables

---

## Project Structure

```
django_backend_starter/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── django_starter/          # Project config package
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── accounts/                # Auth app — register, login, profile
│   ├── models.py            # CustomUser
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── migrations/
├── core/                    # Shared infrastructure
│   ├── renderers.py         # ResponseRenderer — unified response envelope
│   ├── permissions.py       # IsAuthenticatedUser, HavePermissions
│   ├── utils.py             # mail_letter_sender helper
│   ├── views.py             # BaseAPIView, BaseModelViewSet, ping, health, my_ip
│   └── urls.py
├── templates/               # HTML email templates + Swagger UI
│   ├── acc_active_email.html
│   ├── verify_result.html
│   ├── swagger-ui.html
│   └── email/
│       ├── contact_us_email.txt
│       └── password_reset_email.html
├── static/
│   └── geo_lite2/           # Place GeoLite2-City.mmdb here
├── media/
└── logs/
```

---

## Installation

### 1. Clone and create virtual environment

```bash
git clone <your-repo-url>
cd django_backend_starter
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in all required values
```

See [Environment Variables](#environment-variables) for a full reference.

### 4. GeoIP database (optional — required for `/api/my-ip/`)

Download [GeoLite2-City.mmdb](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) from MaxMind and place it at:

```
static/geo_lite2/GeoLite2-City.mmdb
```

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create superuser

```bash
python manage.py createsuperuser
```

### 7. Start development server

```bash
python manage.py runserver
```

API docs available at: [http://localhost:8000/docs/](http://localhost:8000/docs/)

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | — |
| `JWT_SECRET_KEY` | JWT signing key | — |
| `ACCESS_TOKEN_TIME` | Access token lifetime (minutes) | `1440` |
| `REFRESH_TOKEN_TIME` | Refresh token lifetime (minutes) | `10080` |
| `DJANGO_ENV` | `development` or `production` | `production` |
| `HOST` | MySQL host | — |
| `DATABASE_NAME` | MySQL database name | — |
| `DATABASE_USER` | MySQL user | — |
| `DATABASE_PASS` | MySQL password | — |
| `DATABASE_PORT` | MySQL port | `3306` |
| `EMAIL_HOST_USER` | SMTP username | — |
| `EMAIL_HOST_PASSWORD` | SMTP password / app password | — |
| `DEFAULT_FROM_EMAIL` | Sender display name + address | `App <noreply@example.com>` |
| `SUPPORT_EMAIL` | Support contact shown in emails | — |
| `APP_NAME` | App name used in email templates | `App` |
| `LOGO_URL` | Logo URL used in email templates | `""` |
| `CONTACT_US_EMAIL_RECEIVER` | Contact form destination email | — |

---

## API Endpoints

### Authentication
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/register/` | No | Register new user |
| `GET` | `/api/verify-email/<uid>/<token>/` | No | Activate account via email link |
| `GET` | `/api/resend-verify-email/<uidb64>/` | No | Resend activation email |
| `POST` | `/api/token/` | No | Login — returns JWT tokens |
| `POST` | `/api/token/refresh/` | No | Refresh access token |

### Profile
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/profile/` | JWT | Get current user profile |
| `PUT` | `/api/profile/` | JWT | Update profile (partial) |
| `PUT` | `/api/change-password/` | JWT | Change password |

### Utilities
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `HEAD` | `/api/health/` | No | Health check (returns 200) |
| `GET` | `/api/ping/` | No | Ping — returns `"pong"` |
| `GET` | `/api/my-ip/` | No | Client IP + location + device info |

### Documentation
| Endpoint | Description |
|---|---|
| `/docs/` | Swagger UI |
| `/schema/` | OpenAPI schema (JSON) |
| `/admin/` | Django admin |

---

## API Response Format

All responses use the `ResponseRenderer` envelope:

```json
{
  "data": { ... },
  "message": "",
  "status": 200,
  "time": "2026-01-01T00:00:00"
}
```

Paginated responses include `count`, `next`, and `previous` at the top level.

---

## Adding a New App

```bash
python manage.py startapp myapp
```

1. Add `"myapp"` to `INSTALLED_APPS` in `django_starter/settings.py`
2. Extend `BaseModelViewSet` from `core.views` for viewsets
3. Extend `BaseAPIView` or `NoAuthAPIView` from `core.views` for generic views
4. Use `renderers.ResponseRenderer` for consistent response formatting
5. Include your app's `urls.py` in `django_starter/urls.py`

---

## Running Tests

```bash
python manage.py test
```

---

## Deployment Overview

1. Set `DJANGO_ENV=production` in `.env`
2. Run `python manage.py collectstatic`
3. Serve with Gunicorn: `gunicorn django_starter.wsgi:application`
4. Use Nginx as a reverse proxy for static/media files
5. Set `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` appropriately for production

---

## License

MIT
