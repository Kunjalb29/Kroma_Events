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
2. [Architecture & Security Design](#-architecture--security-design)
3. [Quick Start Guide](#-quick-start-guide)
4. [Localhost Quick Reference & URLs](#-localhost-quick-reference--urls)
5. [API Reference](#-api-reference)
6. [Pre-Seeded Test Credentials](#-pre-seeded-test-credentials)
7. [IDE Setup & Import Resolution](#-ide-setup--import-resolution)
8. [Running Automated Tests](#-running-automated-tests)
9. [Production Roadmap](#-production-roadmap)

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
  -d '{"email": "alice@example.com", "password": "Pass1234!", "role": "SEEKER"}'
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

## 🛠️ IDE Setup & Import Resolution

If your editor (VS Code, Pylance, or Pyright) shows module resolution warnings (such as `Cannot find module rest_framework.test`), the project includes pre-configured environment paths:

- **`.vscode/settings.json`:** Directs VS Code to use `./venv/Scripts/python.exe`.
- **`pyrightconfig.json`:** Tells Pyright/Pylance to resolve packages directly from `./venv`.

To select the interpreter in VS Code:
1. Press `Ctrl + Shift + P`.
2. Select **Python: Select Interpreter**.
3. Choose `.\venv\Scripts\python.exe`.

---

## 🧪 Running Automated Tests

The codebase comes with a comprehensive **Pytest** test suite:

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v
```

### Test Coverage Breakdown

| Test File | Coverage Focus |
|---|---|
| `tests/test_otp.py` | OTP hashing, TTL expiry, 3-attempt lockout, resend supersession |
| `tests/test_lifecycle.py` | Registration, verification, login, enrollment & cancellation cycle |
| `tests/test_concurrency.py` | Multi-threaded concurrent enrollment stress testing (`SELECT FOR UPDATE`) |

---

## 📌 Production Roadmap

1. **Email Backend:** Swap development console backend (`EMAIL_BACKEND`) for SendGrid, AWS SES, or SMTP.
2. **PostgreSQL:** Update `.env` variables (`DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) to enable production PostgreSQL with row-level locking.
3. **Rate Limiting:** Implement `django-ratelimit` or API Gateway throttling on authentication endpoints.
4. **Token Revocation:** Enable `rest_framework_simplejwt.token_blacklist` for token invalidation on logout.
