# Kroma Events — Django REST Backend

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/django-5.1-brightgreen.svg)](https://www.djangoproject.com/)
[![REST Framework](https://img.shields.io/badge/DRF-3.17-red.svg)](https://www.django-rest-framework.org/)
[![Auth](https://img.shields.io/badge/JWT-SimpleJWT-orange.svg)](https://django-rest-framework-simplejwt.readthedocs.io/)
[![Tests](https://img.shields.io/badge/tests-9%20passed%20%7C%20100%25-success.svg)](https://docs.pytest.org/)

Production-grade events management platform backend built with **Django 5+**, **Django REST Framework (DRF)**, **SimpleJWT**, and **PostgreSQL** (with zero-config SQLite support for development).

---

## 📋 Table of Contents

1. [Key Features & Highlights](#-key-features--highlights)
2. [Engineering Challenges](#-engineering-challenges)
3. [Architecture & Security Design](#-architecture--security-design)
4. [Quick Start Guide](#-quick-start-guide)
5. [Localhost Quick Reference & URLs](#-localhost-quick-reference--urls)
6. [API Reference](#-api-reference)
7. [Pre-Seeded Test Credentials](#-pre-seeded-test-credentials)
8. [Running Automated Tests](#-running-automated-tests)
9. [IDE Setup & Import Resolution](#-ide-setup--import-resolution)
10. [Known Limitations & Future Improvements](#-known-limitations--future-improvements)

---

## ⚡ Key Features & Highlights

- **Role-Based Access Control (RBAC):** Distinct permissions for `SEEKER` (attending events) and `FACILITATOR` (hosting/managing events).
- **Secure Email OTP Authentication:**
  - 6-digit cryptographically secure OTP generation (`secrets.randbelow`).
  - Stored as SHA-256 hashes (`hashlib`) — plaintext OTPs are never stored or logged.
  - 5-minute TTL & 3-attempt lockout policy to prevent brute-force attacks.
  - Constant-time comparison (`secrets.compare_digest`) to prevent timing attacks.
  - Resend supersession invalidates all previously issued active OTPs.
- **Race Condition & Overbooking Prevention:**
  - Pessimistic locking (`SELECT FOR UPDATE`) combined with atomic DB transactions (`transaction.atomic()`).
  - Enforces capacity limits reliably even under heavy concurrent enrollment requests.
- **Clean REST Contract:** Unified error structure `{"detail": "...", "code": "..."}` across all endpoints.
- **Cross-Platform Ready:** Works out-of-the-box on Windows, macOS, and Linux.

---

## 🧠 Engineering Challenges

The core implementation directly solves three primary engineering challenges:

### A. Enrollment Concurrency
* **Challenge:** Preventing overbooking when multiple seekers attempt simultaneous enrollment for the last available seat (time-of-check/time-of-use race condition).
* **Solution:** Row-level pessimistic locking using `SELECT FOR UPDATE` inside an atomic transaction (`transaction.atomic()`). This serializes concurrent enrollment requests at the database level.
* **Test Suite:** [`tests/test_concurrency.py`](file:///c:/Projects/Kroma_Events/tests/test_concurrency.py) *(Simulates 5 concurrent threads competing for 1 seat).*

### B. Cancellation & Re-enrollment Lifecycle
* **Challenge:** Allowing seekers to cancel and re-enroll while maintaining a complete audit trail without violating database uniqueness constraints or causing overbooking.
* **Solution:** A partial unique index `UniqueConstraint(fields=['event', 'seeker'], condition=Q(status='ENROLLED'))`. Initial enrollment returns `HTTP 201 CREATED`; re-enrollment transitions the existing `CANCELED` row back to `ENROLLED` (`HTTP 200 OK`) if capacity permits.
* **Test Suite:** [`tests/test_lifecycle.py`](file:///c:/Projects/Kroma_Events/tests/test_lifecycle.py) *(Tests initial enrollment, cancellation, capacity reclamation, and re-enrollment).*

### C. OTP Resend & Security Lifecycle
* **Challenge:** Securing email OTP verification without storing plaintext secrets or allowing token reuse / timing attacks.
* **Solution:** SHA-256 hash storage (`hashlib`), 5-minute TTL, 3-attempt max limit, constant-time digest comparison (`secrets.compare_digest`), and automatic supersession of older OTPs on resend.
* **Test Suite:** [`tests/test_otp.py`](file:///c:/Projects/Kroma_Events/tests/test_otp.py) *(Tests OTP hash generation, TTL expiration, 3rd wrong attempt lockout, and resend invalidation).*

> 📄 For in-depth architectural trade-offs and rationale, see [`DECISIONS.md`](file:///c:/Projects/Kroma_Events/DECISIONS.md).

---

## 🏗️ Architecture & Security Design

### Tech Stack Summary

| Layer | Choice | Rationale |
|---|---|---|
| **Framework** | Django 5.1 + DRF 3.17 | Stable, battle-tested foundation for REST APIs |
| **Authentication** | SimpleJWT | Stateless JSON Web Tokens (Access + Refresh pair) |
| **User Model** | `django.contrib.auth.models.User` | Specification compliance; extended via `UserProfile` |
| **Database** | PostgreSQL / SQLite | Pessimistic row locking for concurrency |
| **OTP Hashing** | SHA-256 via `hashlib` | Zero plaintext persistence |
| **Concurrency** | `SELECT FOR UPDATE` + `transaction.atomic()` | Pessimistic locking guarantees zero overbooking |
| **Pagination** | `PageNumberPagination` (default 10) | Standard `{"count", "next", "previous", "results"}` format |

### Data Models & Hierarchy

```
User (Django built-in)
 └─► UserProfile     — role (SEEKER / FACILITATOR), is_verified
     EmailOTP        — otp_hash (SHA-256), expires_at, attempts_count, is_active

Event               — title, description, language, location, starts_at, ends_at, capacity, created_by
Enrollment          — event, seeker, status (ENROLLED / CANCELED), timestamps
```

### Enrollment State Machine

```
    [New Seeker]
         │
         ▼
     ENROLLED ──────► CANCELED
         ▲                │
         └────────────────┘  (Re-enrollment permitted if capacity available)
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.10+** installed on your system.
- Git.

### 1. Clone & Create Virtual Environment

```bash
git clone https://github.com/Kunjalb29/Kroma_Events.git
cd Kroma_Events

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Apply Database Migrations & Seed Data

```bash
# Apply database migrations (SQLite used automatically by default)
python manage.py migrate

# Seed sample users and events
python manage.py seed_data
```

### 4. Run Development Server

```bash
python manage.py runserver
```
The API backend will start listening at `http://127.0.0.1:8000/`.

---

## 🔗 Localhost Quick Reference & URLs

When the dev server is running (`python manage.py runserver`), you can interact with the system via:

| Service / Interface | Localhost URL | Notes / Credentials |
|---|---|---|
| **Django Admin Panel** | [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) | `admin` / `Pass1234!` |
| **DRF Browsable API** | [http://127.0.0.1:8000/api/v1/events/](http://127.0.0.1:8000/api/v1/events/) | Interactive browser testing |
| **API Base URL** | `http://127.0.0.1:8000/api/v1/` | Base prefix for all endpoints |

---

## 📖 API Reference

### 1. Authentication Endpoints (`/api/v1/auth/`)

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/signup/` | None | Register account (`email`, `password`, `role`) |
| `POST` | `/api/v1/auth/verify-otp/` | None | Verify account via 6-digit OTP |
| `POST` | `/api/v1/auth/resend-otp/` | None | Request new OTP code |
| `POST` | `/api/v1/auth/login/` | None | Authenticate → returns JWT Access & Refresh tokens |
| `POST` | `/api/v1/auth/token/refresh/` | None | Refresh JWT access token |
| `GET`  | `/api/v1/auth/me/` | JWT Bearer | Retrieve authenticated user profile |

#### Signup Example
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/signup/ \
  -H "Content-Type: application/json" \
  {"email": "alice@example.com", "password": "Pass1234!", "role": "SEEKER"}
```

#### Login Example
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "Pass1234!"}'
```

---

### 2. Events & Enrollments (`/api/v1/events/`)

| Method | Endpoint | Auth | Allowed Roles | Description |
|---|---|---|---|---|
| `GET` | `/api/v1/events/` | None | Any | List & filter upcoming events |
| `POST` | `/api/v1/events/` | JWT | `FACILITATOR` | Create new event |
| `GET` | `/api/v1/events/<id>/` | None | Any | Retrieve event details |
| `PATCH/PUT` | `/api/v1/events/<id>/` | JWT | Event Creator | Update event details |
| `DELETE` | `/api/v1/events/<id>/` | JWT | Event Creator | Delete event |
| `POST` | `/api/v1/events/<id>/enroll/` | JWT | `SEEKER` | Enroll in event |
| `POST` | `/api/v1/events/<id>/cancel/` | JWT | `SEEKER` | Cancel enrollment |
| `GET` | `/api/v1/events/my-enrollments/` | JWT | `SEEKER` | List authenticated user's enrollments |

---

## 🔑 Pre-Seeded Test Credentials

Running `python manage.py seed_data` populates the database with the following demo accounts:

| Role | Username / Email | Password | Status |
|---|---|---|---|
| **Superuser / Admin** | `admin` / `admin@kroma.dev` | `Pass1234!` | Verified |
| **Facilitator** | `facilitator@kroma.dev` | `Pass1234!` | Verified |
| **Seeker 1** | `seeker1@kroma.dev` | `Pass1234!` | Verified |
| **Seeker 2** | `seeker2@kroma.dev` | `Pass1234!` | Verified |

---

## 🧪 Running Automated Tests

The codebase includes a comprehensive **Pytest** test suite covering all mandatory assignment requirements.

### Full Test Suite
```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v
```

### Assignment Challenge Test Suites
To evaluate specific assignment requirements individually:

```bash
# Challenge A: Enrollment Concurrency & Race Conditions
pytest -v tests/test_concurrency.py

# Challenge B: Cancellation & Re-enrollment Lifecycle
pytest -v tests/test_lifecycle.py

# Challenge C: OTP Security & Resend Supersession
pytest -v tests/test_otp.py
```

### Test Coverage Summary

| Test Suite | Focus Area |
|---|---|
| [`tests/test_concurrency.py`](file:///c:/Projects/Kroma_Events/tests/test_concurrency.py) | 5 concurrent seekers competing for 1 seat $\rightarrow$ exactly 1 succeeds, zero overbooking |
| [`tests/test_lifecycle.py`](file:///c:/Projects/Kroma_Events/tests/test_lifecycle.py) | Enroll/cancel/re-enroll cycle, duplicate enrollment rejection, capacity reclamation |
| [`tests/test_otp.py`](file:///c:/Projects/Kroma_Events/tests/test_otp.py) | OTP SHA-256 hashing, 5-min TTL expiry, 3-attempt lockout, resend supersession |

---

## 🛠️ IDE Setup & Import Resolution

If your editor (VS Code, Pylance, or Pyright) shows module resolution warnings (such as `Cannot find module rest_framework.test`), the project includes pre-configured environment paths:

- **`.vscode/settings.json`:** Directs VS Code to use `./venv/Scripts/python.exe`.
- **`pyrightconfig.json`:** Tells Pyright/Pylance to resolve packages directly from `./venv`.

To select the interpreter in VS Code:
1. Press `Ctrl + Shift + P`.
2. Select **Python: Select Interpreter**.
3. Choose `.\venv\Scripts\python.exe`.

---

## ⚠️ Known Limitations & Future Improvements

While the application meets all specification requirements, the following improvements are noted for production readiness:

1. **Database Engine:** SQLite is configured by default for zero-setup local development and automated testing; PostgreSQL (supported via `.env`) is recommended for production environments requiring true row-level MVCC write locking.
2. **Email Delivery Backend:** Currently uses Django's console email backend (`django.core.mail.backends.console.EmailBackend`) for local testing. In production, configure an SMTP service or cloud provider (e.g. SendGrid or AWS SES) via environment variables.
3. **Production Rate Limiting:** Authentication and OTP generation endpoints currently lack rate limiting. In production, integrate `django-ratelimit` or an API gateway throttling layer to prevent abuse.
4. **JWT Revocation / Blacklisting:** SimpleJWT refresh tokens are stateless by default. For explicit logout and token revocation support, enable `rest_framework_simplejwt.token_blacklist` in `INSTALLED_APPS`.
5. **Interactive API Documentation:** OpenAPI / Swagger documentation UI can be auto-generated by adding `drf-spectacular` or `drf-yasg`.
