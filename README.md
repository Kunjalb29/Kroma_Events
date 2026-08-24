# Kroma Events — Django REST Backend

Production-grade events platform backend built with Django 4+, DRF, SimpleJWT, and PostgreSQL.

---

## Table of Contents
1. [Architecture Summary](#architecture-summary)
2. [Setup & Run](#setup--run)
3. [API Reference](#api-reference)
4. [Seed Data](#seed-data)
5. [Running Tests](#running-tests)
6. [Known Limitations & Future Improvements](#known-limitations--future-improvements)

---

## Architecture Summary

| Layer | Choice | Rationale |
|---|---|---|
| Framework | Django 4.2 + DRF 3.14 | Stable LTS; battle-tested for REST APIs |
| Auth | SimpleJWT | Stateless, access+refresh token pair |
| User model | `django.contrib.auth.models.User` | Spec requirement; `UserProfile` extends via `OneToOneField` |
| Database | PostgreSQL (SQLite fallback for tests) | Row-level locking (`SELECT FOR UPDATE`) for concurrency |
| OTP hash | SHA-256 via `hashlib` | Plaintext never stored or logged |
| OTP generation | `secrets.randbelow` | Cryptographically secure PRNG |
| Concurrency | `SELECT FOR UPDATE` + `transaction.atomic` | Pessimistic lock prevents overbooking |
| Errors | `{"detail": "...", "code": "..."}` | Consistent API contract across all endpoints |
| Pagination | `PageNumberPagination` (page_size=10) | `{"count", "next", "previous", "results"}` |

### Models
```
User (Django built-in)
 └─► UserProfile     — role (SEEKER/FACILITATOR), is_verified
     EmailOTP        — otp_hash (SHA-256), expires_at, attempts_count, is_active

Event               — title, description, language, location, starts_at, ends_at, capacity, created_by
Enrollment          — event, seeker, status (ENROLLED/CANCELED), timestamps
                      partial unique: (event, seeker) WHERE status='ENROLLED'
```

### OTP Security Design
- **Stored**: SHA-256(plaintext_OTP) — 64-char hex
- **TTL**: 5 minutes
- **Attempts**: max 3; 3rd failure deactivates the token permanently
- **Resend**: new OTP supersedes (deactivates) all prior active tokens
- **Comparison**: `secrets.compare_digest` (constant-time, prevents timing attacks)

### Enrollment State Machine
```
    [New Seeker]
         │
         ▼
     ENROLLED ──────► CANCELED
         ▲                │
         └────────────────┘  (re-enrollment if capacity permits)
```
Database constraint: `UniqueConstraint(fields=['event','seeker'], condition=Q(status='ENROLLED'))`
→ Only one active enrollment per (seeker, event) pair at the DB level.

---

## Setup & Run

### Prerequisites
- Python 3.10+
- (Optional) PostgreSQL 13+ for production mode

### 1. Clone & Create Virtual Environment
```bash
git clone https://github.com/Kunjalb29/Kroma_Events.git
cd Kroma_Events
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
# Copy and edit the example env file
cp .env.example .env
```

**SQLite (default — no config needed):**
No changes required. `db.sqlite3` will be used automatically.

**PostgreSQL:**
Edit `.env`:
```
DB_ENGINE=django.db.backends.postgresql
DB_NAME=kroma_events
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432
```

### 4. Run Migrations
```bash
python manage.py migrate
```

### 5. (Optional) Seed Sample Data
```bash
python manage.py seed_data
# Creates: facilitator@kroma.dev / Pass1234!
#          seeker1@kroma.dev / Pass1234!
#          seeker2@kroma.dev / Pass1234!
#          3 upcoming Events
```

### 6. Start Development Server
```bash
python manage.py runserver
```
API is available at: `http://127.0.0.1:8000/`

### 7. (Optional) Django Admin
```bash
python manage.py createsuperuser
# Visit http://127.0.0.1:8000/admin/
```

---

## API Reference

### Base URL: `http://127.0.0.1:8000/api/v1/`

### Authentication Endpoints (`/auth/`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup/` | None | Register user (email, password, role) |
| POST | `/auth/verify-otp/` | None | Verify email with 6-digit OTP |
| POST | `/auth/resend-otp/` | None | Resend OTP (supersedes prior) |
| POST | `/auth/login/` | None | Login → access + refresh tokens |
| POST | `/auth/token/refresh/` | None | Refresh access token |
| GET  | `/auth/me/` | JWT | Get own profile |

#### Signup
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "Pass1234!", "role": "SEEKER"}'
```
Response `201`:
```json
{
  "detail": "Account created successfully. A 6-digit verification code has been sent to your email address.",
  "email": "alice@example.com",
  "role": "SEEKER",
  "is_verified": false
}
```

#### Verify OTP
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "otp": "482915"}'
```
> **Note**: In development, the OTP is printed to the Django console (EMAIL_BACKEND=console).

#### Login
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "Pass1234!"}'
```
Response `200`:
```json
{
  "access": "<jwt_access_token>",
  "refresh": "<jwt_refresh_token>",
  "user": {"id": 1, "email": "alice@example.com", "role": "SEEKER", "is_verified": true}
}
```

### Event Endpoints (`/events/`)

| Method | Endpoint | Auth | Role | Description |
|---|---|---|---|---|
| GET | `/events/` | Optional | Any | List/search events (paginated) |
| POST | `/events/` | JWT | FACILITATOR | Create event |
| GET | `/events/<id>/` | JWT | Any | Retrieve event detail |
| PATCH/PUT | `/events/<id>/` | JWT | FACILITATOR+Owner | Update event |
| DELETE | `/events/<id>/` | JWT | FACILITATOR+Owner | Delete event |
| POST | `/events/<id>/enroll/` | JWT | SEEKER | Enroll in event |
| POST | `/events/<id>/cancel/` | JWT | SEEKER | Cancel enrollment |
| GET | `/events/my-enrollments/` | JWT | SEEKER | List own enrollments |

#### Search Parameters (GET `/events/`)
| Param | Type | Description |
|---|---|---|
| `q` | string | Full-text search in title + description |
| `location` | string | Filter by location (case-insensitive) |
| `language` | string | Filter by language |
| `starts_after` | ISO-8601 | Events starting after this datetime |
| `starts_before` | ISO-8601 | Events starting before this datetime |
| `page` | int | Page number |
| `page_size` | int | Results per page (max 100) |

#### Create Event (Facilitator)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/events/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Django Workshop",
    "description": "Learn advanced DRF patterns",
    "language": "English",
    "location": "Online",
    "starts_at": "2026-09-15T10:00:00Z",
    "ends_at": "2026-09-15T13:00:00Z",
    "capacity": 50
  }'
```

### Error Response Shape
All errors follow:
```json
{"detail": "Human-readable message.", "code": "machine_readable_code"}
```

| Code | HTTP | Description |
|---|---|---|
| `otp_invalid` | 400 | Wrong OTP code |
| `otp_expired` | 400 | OTP TTL exceeded |
| `otp_max_attempts_exceeded` | 400 | 3 wrong attempts |
| `already_verified` | 400 | Account already verified |
| `user_unverified` | 403 | Login before verification |
| `invalid_credentials` | 401 | Wrong email/password |
| `capacity_full` | 400 | Event at capacity |
| `already_enrolled` | 400 | Seeker already enrolled |
| `enrollment_not_found` | 404 | No active enrollment to cancel |
| `permission_denied` | 403 | Role/ownership violation |
| `invalid_input` | 400 | Serializer validation error |

---

## Seed Data

```bash
python manage.py seed_data
```

| Account | Email | Password | Role |
|---|---|---|---|
| Facilitator | facilitator@kroma.dev | Pass1234! | FACILITATOR |
| Seeker 1 | seeker1@kroma.dev | Pass1234! | SEEKER |
| Seeker 2 | seeker2@kroma.dev | Pass1234! | SEEKER |

3 upcoming Events are also created (next 3/7/14 days).

---

## Running Tests

```bash
# All tests
pytest

# Verbose output
pytest -v

# Specific test file
pytest tests/test_otp.py -v
pytest tests/test_lifecycle.py -v
pytest tests/test_concurrency.py -v
```

### Test Coverage Summary

| File | What it tests |
|---|---|
| `test_otp.py` | OTP hash storage, verification, TTL expiry, 3-attempt lockout, resend supersession |
| `test_lifecycle.py` | Enroll/cancel/re-enroll cycle, duplicate rejection, capacity reclamation |
| `test_concurrency.py` | 5 concurrent seekers, 1 seat remaining → exactly 1 success, no overbooking |

---

## Known Limitations & Future Improvements

1. **Email backend**: Uses Django console backend for development. In production, swap for SendGrid/SES/SMTP via `EMAIL_BACKEND` environment variable.
2. **OTP not returned in API**: By design. The console backend prints it to stdout for local dev. A real SMTP provider would deliver it to the user's inbox.
3. **No rate limiting**: Signup and OTP endpoints should be rate-limited (e.g., `django-ratelimit` or an API gateway) in production.
4. **No token blacklisting**: JWT refresh tokens are stateless. For revocation, add `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS`.
5. **Pagination on all list views**: Events list is paginated. Enrollment list is also paginated but typically small for a single user.
6. **Docker Compose**: Adding a `docker-compose.yml` with PostgreSQL + Django would simplify local setup.
7. **Event past-date validation**: Currently events can be created with `starts_at` in the past. A production system should reject this.
8. **Soft-delete for Events**: Deleting an event cascades to its enrollments. A soft-delete approach would preserve audit history.
