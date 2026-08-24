# Kroma Events Platform - Production-Grade Django REST API

A highly reliable, production-grade Django REST Framework backend for an Events Platform. Built with explicit concurrency protections, role-based access control, partial unique index state machines, custom error handling, and robust OTP authentication.

---

## 🏛️ Architectural Overview

- **Framework**: Django 5.1 & Django REST Framework (DRF).
- **Authentication**: Built-in Django `django.contrib.auth.models.User` combined with `UserProfile` (`SEEKER` / `FACILITATOR`). SimpleJWT for JWT token issuance.
- **Database**: PostgreSQL default with automatic fallback to SQLite for local development and test execution.
- **Concurrency & Locking**: Pessimistic row locking (`select_for_update()`) executed inside database transactions (`transaction.atomic()`) ensuring capacity limits are strictly enforced under high concurrency.
- **State Machine**: Enrollment state transitions (`ENROLLED` ↔ `CANCELED`) backed by a Django `UniqueConstraint(condition=Q(status='ENROLLED'))` partial index.
- **Error Standard**: Universal error format across all exceptions: `{"detail": "...", "code": "..."}`.
- **Pagination Standard**: Consistent pagination shape across all list endpoints: `{"count": N, "next": null, "previous": null, "results": [...]}`.

---

## 🚀 Environment Setup & Installation

### 1. Prerequisites
- Python 3.10+
- PostgreSQL (optional for local production testing; SQLite works out-of-the-box)

### 2. Virtual Environment Setup
```bash
# Clone the repository
git clone https://github.com/Kunjalb29/Kroma_Events.git
cd Kroma_Events

# Create and activate virtual environment
python -m venv venv

# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# On Linux/macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables
Create a `.env` file from the provided example:
```bash
cp .env.example .env
```
Default `.env` settings:
```env
DEBUG=True
SECRET_KEY=django-insecure-kroma-events-secret-key-production-grade
ALLOWED_HOSTS=localhost,127.0.0.1
# DATABASE_URL=sqlite:///db.sqlite3
```

### 5. Database Migrations
```bash
python manage.py makemigrations users events
python manage.py migrate
```

---

## 🧪 Automated Test Suite

The test suite covers multi-threaded race conditions, OTP lifecycle policy, and enrollment state transitions:

```bash
# Run pytest suite
pytest

# Run pytest with verbose output
pytest -v
```

### Included Test Files:
1. `tests/test_concurrency.py`: 5 concurrent threads attempting enrollment on a capacity=10 event with 9 seats taken. Guarantees exactly 1 succeeds and 4 fail with `code='capacity_full'`.
2. `tests/test_lifecycle.py`: Validates enroll -> cancel -> re-enroll transitions, partial unique constraint, and capacity reclamation.
3. `tests/test_otp.py`: Validates 5-minute TTL expiration, 3-attempt lockout policy, single-active OTP supersession on resend, and account verification.

---

## 📬 API Endpoint Documentation & Curl Reference

### 1. Signup (`POST /api/v1/auth/signup/`)
Rejects any incoming `username` field; autogenerates clean unique username. Sends 6-digit OTP code to console.

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "seeker@example.com",
    "password": "SecurePassword123!",
    "role": "SEEKER"
  }'
```

**Response (201 Created):**
```json
{
  "detail": "User registered successfully. An OTP has been sent to your email address.",
  "email": "seeker@example.com",
  "role": "SEEKER",
  "is_verified": false
}
```

---

### 2. Verify OTP (`POST /api/v1/auth/verify-otp/`)
Verifies SHA-256 hashed OTP code.

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "seeker@example.com",
    "otp": "123456"
  }'
```

**Response (200 OK):**
```json
{
  "detail": "Email verified successfully. You can now log in.",
  "is_verified": true
}
```

---

### 3. Resend OTP (`POST /api/v1/auth/resend-otp/`)
Invalidates prior active OTPs and generates a fresh 5-minute TTL OTP.

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/resend-otp/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "seeker@example.com"
  }'
```

**Response (200 OK):**
```json
{
  "detail": "A new OTP has been sent to your email address."
}
```

---

### 4. Login (`POST /api/v1/auth/login/`)
Blocks unverified users (`is_verified=false`). Returns JWT tokens upon verification.

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "seeker@example.com",
    "password": "SecurePassword123!"
  }'
```

**Response (200 OK):**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "email": "seeker@example.com",
    "role": "SEEKER",
    "is_verified": true
  }
}
```

---

### 5. Create Event (Facilitator Only) (`POST /api/v1/events/`)

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/events/ \
  -H "Authorization: Bearer <FACILITATOR_JWT_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Django Concurrency Masterclass",
    "description": "Deep dive into pessimistic locking and row isolation.",
    "language": "English",
    "location": "Online - Zoom",
    "starts_at": "2026-09-01T10:00:00Z",
    "ends_at": "2026-09-01T12:00:00Z",
    "capacity": 50
  }'
```

**Response (201 Created):**
```json
{
  "id": 1,
  "title": "Django Concurrency Masterclass",
  "description": "Deep dive into pessimistic locking and row isolation.",
  "language": "English",
  "location": "Online - Zoom",
  "starts_at": "2026-09-01T10:00:00Z",
  "ends_at": "2026-09-01T12:00:00Z",
  "capacity": 50,
  "created_by": 2,
  "created_by_email": "facilitator@example.com",
  "enrolled_count": 0,
  "available_seats": 50,
  "created_at": "2026-08-24T18:00:00Z",
  "updated_at": "2026-08-24T18:00:00Z"
}
```

---

### 6. List & Search Events (`GET /api/v1/events/`)
Supports filtering by `q`, `location`, `language`, `starts_after`, `starts_before`. Default ordering: upcoming first (`starts_at` ASC).

**Request:**
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/events/?q=concurrency&location=Online&starts_after=2026-08-01T00:00:00Z"
```

**Response (200 OK):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Django Concurrency Masterclass",
      "description": "Deep dive into pessimistic locking and row isolation.",
      "language": "English",
      "location": "Online - Zoom",
      "starts_at": "2026-09-01T10:00:00Z",
      "ends_at": "2026-09-01T12:00:00Z",
      "capacity": 50,
      "created_by": 2,
      "created_by_email": "facilitator@example.com",
      "enrolled_count": 0,
      "available_seats": 50,
      "created_at": "2026-08-24T18:00:00Z",
      "updated_at": "2026-08-24T18:00:00Z"
    }
  ]
}
```

---

### 7. Enroll in Event (Seeker Only) (`POST /api/v1/events/1/enroll/`)

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/events/1/enroll/ \
  -H "Authorization: Bearer <SEEKER_JWT_ACCESS_TOKEN>"
```

**Response (201 Created):**
```json
{
  "detail": "Successfully enrolled in event.",
  "enrollment": {
    "id": 1,
    "event": 1,
    "event_title": "Django Concurrency Masterclass",
    "event_starts_at": "2026-09-01T10:00:00Z",
    "seeker": 1,
    "seeker_email": "seeker@example.com",
    "status": "ENROLLED",
    "created_at": "2026-08-24T18:05:00Z",
    "updated_at": "2026-08-24T18:05:00Z"
  }
}
```

---

### 8. Cancel Enrollment (Seeker Only) (`POST /api/v1/events/1/cancel/`)

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/events/1/cancel/ \
  -H "Authorization: Bearer <SEEKER_JWT_ACCESS_TOKEN>"
```

**Response (200 OK):**
```json
{
  "detail": "Enrollment successfully canceled.",
  "enrollment": {
    "id": 1,
    "event": 1,
    "event_title": "Django Concurrency Masterclass",
    "event_starts_at": "2026-09-01T10:00:00Z",
    "seeker": 1,
    "seeker_email": "seeker@example.com",
    "status": "CANCELED",
    "created_at": "2026-08-24T18:05:00Z",
    "updated_at": "2026-08-24T18:10:00Z"
  }
}
```

---

## 🔮 Future Improvements

1. **Redis-backed Celery Task Queue**: Asynchronous OTP email dispatching to eliminate blocking HTTP latency on signup/resend.
2. **WebSockets (Django Channels)**: Real-time event capacity updates pushed live to client frontends when available seats drop to zero.
3. **Full-Text Search (PostgreSQL `SearchVector`)**: Upgrade `icontains` queries to full-text search with ranking and stemmed keyword matching across title and description.
