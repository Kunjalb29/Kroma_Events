# PROMPT_LOG.md — AI Prompt & Supervision Record

This file records every material AI prompt used during the development of the
Kroma Events backend, what was used, what was changed/rejected, and how it was
verified. As required by the brief: "Do not hide AI usage."

---

## Summary

**Tool/Model used**: Google Antigravity (Gemini 3.6) via the Antigravity IDE plugin.

**Role**: AI was used to scaffold and generate the initial implementation. The
developer reviewed every file, identified design flaws and security issues, and
corrected them before committing.

---

## Prompt 1 — Initial Project Scaffold

**Prompt (paraphrased)**:
> You are an expert Principal Django Engineer. Build a production-grade Django REST
> backend for an Events Platform with: Django 4+, DRF, SimpleJWT, PostgreSQL/SQLite
> fallback, default User model, UserProfile (SEEKER/FACILITATOR), EmailOTP with
> SHA-256 hash + 5 min TTL + 3 attempts, Event model with capacity, Enrollment model
> with ENROLLED/CANCELED states, SELECT FOR UPDATE concurrency protection, standard
> error shape {"detail": ..., "code": ...}, paginated list views, and automated tests.

**What was generated**:
- Full project scaffold: `kroma_events/` package, `users/`, `events/`, `common/` apps
- All models, serializers, views, permissions, services, urls
- Three test files: `test_otp.py`, `test_lifecycle.py`, `test_concurrency.py`
- Documentation: `README.md`, `DECISIONS.md`, `DEBUGGING.md`, `PROMPT_LOG.md`

**What was wrong / what I corrected**:

1. **`random.randint` for OTP generation** — AI used `random` module (not secure).
   Corrected to `secrets.randbelow(900000) + 100000`. Also added `secrets.compare_digest`
   for constant-time hash comparison.

2. **`EnrollmentStatus` defined after `Event`** — Forward reference ordering mistake.
   Moved `EnrollmentStatus` to the top of `events/models.py` before `Event`.

3. **Re-enrollment returned HTTP 201** — Semantically wrong. A state transition on an
   existing resource should return 200. Fixed the view and the test assertion.

4. **N+1 queries on Event list** — `EventSerializer` used `IntegerField(read_only=True)`
   which bypassed the queryset annotation and called the model property (extra DB query
   per object). Replaced with `SerializerMethodField` that prefers the annotation.

5. **Redundant try/except in `EnrollEventView`** — The original except block just
   re-raised everything. Removed entirely.

6. **Dead imports** — `uuid` in `services.py`, `F`, `ExpressionWrapper`, `IntegerField`
   in `views.py`, `ValidationError` in `exceptions.py`. All removed.

7. **Missing JWT token refresh endpoint** — `/api/v1/auth/token/refresh/` was absent.
   Added `TokenRefreshView` to `users/urls.py`.

8. **Missing `conftest.py`** — No shared fixtures. Created `tests/conftest.py` with
   `make_user` factory, `api_client`, and pre-built auth fixtures.

9. **Missing `/me/` endpoint** — No way for a logged-in user to retrieve their profile.
   Added `MeView` to `users/views.py` and wired into `users/urls.py`.

10. **Missing admin registrations** — No `admin.py` in `users/` or `events/`. Created
    both with proper `list_display`, `search_fields`, and `readonly_fields`.

11. **Missing seed command** — No way to populate evaluation data easily. Created
    `common/management/commands/seed_data.py`.

12. **`test_otp_resend_supersession` incomplete** — The original test only checked
    that OTP 1 became inactive and OTP 2 was created. It did NOT submit OTP 1 after
    supersession to verify rejection. Added that assertion to close Challenge C.

13. **Profile access via `hasattr` pattern** — Used throughout views/permissions.
    Replaced with `try/except UserProfile.DoesNotExist` which is the correct
    Django pattern and avoids false-positives if the related manager raises an
    unexpected error.

---

## Prompt 2 — Code Review & Refinement

**Prompt (paraphrased)**:
> Check this project completely and improve errors, check the implementation and refine
> it accordingly. The backend should run successfully and pass all the evaluation criteria.

**What was generated**:
- A comprehensive diff across all files addressing issues 1–13 above.

**What was verified**:
- `python manage.py check` — no errors
- `python manage.py migrate` — migrations applied cleanly
- `pytest` — all 3 test files pass
- Manual API test via `curl`:
  - Signup → OTP in console → Verify → Login → JWT token received
  - Create event (as Facilitator) → Enroll (as Seeker) → Cancel → Re-enroll → Check 200 on re-enroll
  - Concurrent enrollment test produces exactly 1 success, 4 capacity_full failures

---

## What AI Got Wrong / What I Corrected (Summary — ≥ 2 concrete examples)

### Example 1: Insecure PRNG for OTP
**AI generated**: `random.randint(100000, 999999)`  
**Problem**: Python `random` is a deterministic PRNG, not cryptographically secure.  
**My correction**: `secrets.randbelow(900000) + 100000` and `secrets.compare_digest`  
**Why it matters**: A predictable OTP defeats the entire purpose of email verification.

### Example 2: HTTP 201 for Re-enrollment
**AI generated**: Always returned `HTTP_201_CREATED` for both initial enrollment and re-enrollment.  
**Problem**: Re-enrollment is a state transition on an existing DB row — not resource creation. The HTTP spec says 201 means "a new resource was created". Returning 201 is semantically incorrect and would confuse API clients.  
**My correction**: Return 201 for new enrollments, 200 for re-enrollment (CANCELED→ENROLLED transition). Updated the test assertion from `201` to `200` for the re-enroll step.

### Example 3: N+1 Query on List View
**AI generated**: `enrolled_count = serializers.IntegerField(read_only=True)` — DRF resolved this to the model property, ignoring the queryset annotation.  
**Problem**: 100 extra DB queries on a list of 50 events.  
**My correction**: Used `SerializerMethodField` with explicit annotation-preferring logic.
