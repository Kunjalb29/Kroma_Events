# Architectural Decision Records (ADR) - Kroma Events Platform

This document records three critical architectural decisions made during the design and implementation of the Kroma Events REST platform.

---

## 1. Concurrency Strategy: Pessimistic Row Locking (`select_for_update`) vs. Optimistic Locking / DB Triggers

### Context & Challenge
In high-throughput event platforms (e.g., ticket drops, flash registrations), concurrent enrollment requests targeting an event near full capacity inevitably produce race conditions. Without explicit locking, two parallel database transactions can read `enrolled_count = 9` for an event with `capacity = 10`, evaluate that a seat remains, insert two new `ENROLLED` records, and cause overbooking (`enrolled_count = 11`).

### Alternatives Considered
1. **Optimistic Locking (Version / ETags)**: Requires adding a `version` field to `Event`. Each transaction reads the version, calculates capacity, and updates with `WHERE version = read_version`.
   - *Drawback*: Under high contention (e.g., 50 concurrent requests for 1 seat), 49 requests fail with optimistic concurrency conflicts and must be retried client-side or loop-retried inside Django, burning CPU and connection pool bandwidth.
2. **Database Triggers / Stored Procedures**: Placing seat calculation and check constraints inside raw PostgreSQL triggers.
   - *Drawback*: Ties business logic directly to PostgreSQL SQL scripts, complicates Django ORM migrations, and hinders testability under SQLite local test environments.
3. **Pessimistic Row Locking (`select_for_update()`)**:
   - *Chosen Approach*: Wrap enrollment execution inside `transaction.atomic()` and acquire an explicit row lock on the target `Event` instance using `Event.objects.select_for_update().get(id=pk)`.

### Decision Rationale
Pessimistic row locking guarantees strict serializability at the row level for the specific `Event` being enrolled in, without locking unrelated database rows or tables. 
- When 5 concurrent requests arrive for the last remaining seat, PostgreSQL places 4 transactions in a queued wait state behind the locked row.
- The 1st transaction enters, counts `status='ENROLLED'` rows inside the lock (finding 9), inserts the 10th row, and commits.
- The 2nd transaction acquires the lock, re-reads `status='ENROLLED'` rows inside its transaction (now finding 10), evaluates `10 >= capacity`, raises `CapacityFullException`, and rolls back.
- All remaining transactions cleanly fail with `capacity_full` without overbooking or requiring complex retry back-offs.

---

## 2. Re-enrollment Lifecycle: Partial Unique Constraint (`status='ENROLLED'`) vs. Single Mutable State Record

### Context & Challenge
A seeker can enroll in an event, cancel their enrollment, and subsequently re-enroll if seats remain available. We needed an database-enforced integrity constraint to ensure a seeker can never hold 2 active `ENROLLED` records for the same event simultaneously, while preserving historical records of previous cancellations.

### Alternatives Considered
1. **Single Mutable Enrollment Record**: Maintain exactly 1 row per `(event, seeker)` tuple and update `status` in place (`ENROLLED` → `CANCELED` → `ENROLLED`).
   - *Drawback*: Destroys historical audit trails of when previous cancellations occurred and prevents analytics tracking of seeker cancellation frequencies over time.
2. **Unconstrained Multiple Insertions with Application-Level Checks**: Insert a new `Enrollment` row on every action without a database unique constraint.
   - *Drawback*: Fails to prevent duplicate active enrollments if application-level checks are bypassed during concurrent API calls.
3. **Django Partial Unique Constraint (`UniqueConstraint` with `condition=Q(status='ENROLLED')`)**:
   - *Chosen Approach*: Implement a partial index in Django models:
     ```python
     models.UniqueConstraint(
         fields=['event', 'seeker'],
         condition=models.Q(status='ENROLLED'),
         name='unique_active_enrollment_per_seeker'
     )
     ```

### Decision Rationale
The Partial Unique Index delegates active enrollment uniqueness directly to the database engine.
- PostgreSQL creates a conditional unique index that only indexing rows where `status = 'ENROLLED'`.
- A seeker can have multiple historical `CANCELED` rows without violating uniqueness.
- When re-enrolling, the system searches for an existing `CANCELED` record and transitions its status back to `ENROLLED` under `select_for_update()`, or inserts a new row if none exists.
- If a race condition occurs where two requests attempt to enroll the same seeker concurrently, the partial unique index aborts the second insert at the database boundary with an `IntegrityError`.

---

## 3. OTP Security Policy: Hashed Storage & Single-Active OTP Supersession vs. Rolling Valid Tokens

### Context & Challenge
One-Time Passwords (OTPs) generated during account signup and email verification present security risks if stored in plaintext or if multiple valid OTPs remain active simultaneously.

### Alternatives Considered
1. **Rolling Valid Tokens**: Allow multiple active OTPs to coexist until each individual 5-minute TTL expires.
   - *Drawback*: Increases brute-force surface area (a user who requests 5 OTPs within 2 minutes has 5 valid targets for an attacker to guess).
2. **Plaintext OTP Storage**: Storing the 6-digit code directly in database columns.
   - *Drawback*: Exposes user verification codes if a database snapshot or read-replica leak occurs.
3. **SHA-256 Hashed Storage with Single-Active Supersession**:
   - *Chosen Approach*: 
     - Store only the SHA-256 hash (`hashlib.sha256(otp.encode()).hexdigest()`) in `EmailOTP.otp_hash`.
     - Enforce a Single-Active OTP policy: generating or resending an OTP immediately marks all previous active OTP records for that user as `is_active = False`.
     - Enforce 5-minute TTL, max 3 failed verification attempts before permanent invalidation, and console/file email backend delivery only.

### Decision Rationale
- **Zero-Plaintext Exposure**: Plaintext OTP codes are created in memory, sent via Django's email backend, and immediately discarded. No log file, API response payload, or database table ever stores plaintext OTPs.
- **Minimizing Brute-Force Windows**: The combination of SHA-256 hashing, 3-attempt hard lockout limit, 5-minute expiration window, and single-active token supersession reduces the total statistical probability of a successful brute-force attack to less than 0.0003%.
