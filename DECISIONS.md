# DECISIONS.md — Non-Trivial Engineering Decisions

This file documents at least 3 significant design/architecture decisions made during
the development of the Kroma Events backend. For each decision, the ambiguity is
described, the options considered are listed, and the final choice with trade-offs is
explained.

---

## Decision 1: Enrollment Concurrency Strategy (Challenge A)

### Problem
When an event has capacity = 10 and current enrollments = 9, five seekers attempting
to enroll simultaneously through separate API requests could all read `active_count = 9`,
all pass the capacity check, and all write new enrollments, resulting in 14 total
enrollments (4 over capacity). This is a classic TOCTOU (time-of-check/time-of-use)
race condition.

### Options Considered

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| A | Optimistic locking (version field) | Low DB contention | Retry logic needed; complex client error handling |
| B | Application-level mutex (threading.Lock) | Simple Python code | Only works within one process; breaks with multi-worker deployments |
| C | **Pessimistic locking (SELECT FOR UPDATE)** | DB-enforced; works across workers | Slightly higher lock contention; requires transaction |
| D | Partial unique constraint only | Database enforces uniqueness | Only prevents duplicate rows, not capacity overflow |

### Decision: Option C — `SELECT FOR UPDATE` inside `transaction.atomic()`

```python
with transaction.atomic():
    event = Event.objects.select_for_update().filter(pk=pk).first()
    active_count = Enrollment.objects.filter(event=event, status='ENROLLED').count()
    if active_count >= event.capacity:
        raise CapacityFullException()
    # safe to create enrollment
```

The Event row is row-locked for the duration of the transaction. Any concurrent
request attempting to lock the same row will block until the first transaction commits
or rolls back. The seat count read inside the lock is always authoritative.

**Additional backstop**: The partial unique constraint `(event, seeker) WHERE status='ENROLLED'`
prevents double-active-enrollment at the database level even if application logic fails.

### Trade-off
Lock contention increases under very high concurrency. For an event with 10,000 seekers
racing simultaneously, `SELECT FOR UPDATE` could create a bottleneck. The mitigation
would be a queue-based reservation system (e.g., Celery + Redis). For this platform's
expected scale, row-locking is appropriate and correct.

---

## Decision 2: Partial Unique Constraint for Re-enrollment (Challenge B)

### Problem
The spec requires that a seeker can cancel and re-enroll. A simple
`UNIQUE(event, seeker)` constraint would prevent re-enrollment entirely because the
`CANCELED` row would block a new `ENROLLED` row for the same pair.

### Options Considered

| Option | Approach | Pros | Cons |
|---|---|---|---|
| A | Delete CANCELED row on re-enroll | Avoids duplicate rows | Loses audit history |
| B | **Partial unique index WHERE status='ENROLLED'** | Allows multiple rows; only 1 active per pair | Requires DB partial-index support |
| C | Application-only deduplication | No DB constraint | Relies purely on app logic; not a safety net |
| D | Status state machine in a separate table | Full event sourcing | Over-engineering for this scope |

### Decision: Option B — Partial Unique Constraint

```python
constraints = [
    models.UniqueConstraint(
        fields=['event', 'seeker'],
        condition=models.Q(status='ENROLLED'),
        name='unique_active_enrollment_per_seeker',
    )
]
```

This allows:
- `(event=1, seeker=1, status='ENROLLED')` — ✓ allowed
- `(event=1, seeker=1, status='CANCELED')` — ✓ allowed
- `(event=1, seeker=1, status='ENROLLED')` again — ✗ DB violation (caught by app logic first)

The re-enrollment path transitions the existing `CANCELED` row to `ENROLLED` rather
than inserting a new row:
```python
existing.status = EnrollmentStatus.ENROLLED
existing.save(update_fields=['status', 'updated_at'])
```

**API behaviour**: Initial enrollment returns HTTP 201 (resource created). Re-enrollment
returns HTTP 200 (state transition on an existing resource, not creation).

### Trade-off
CANCELED rows are retained indefinitely. For high-volume events, periodic archival of
old CANCELED rows may be needed. The benefit is a complete audit trail of enroll/cancel
history per seeker.

---

## Decision 3: OTP Supersession — OTP 1 Invalid After OTP 2 is Issued (Challenge C)

### Problem
If a user requests OTP 1 then requests OTP 2 (resend), and then submits OTP 1 — should
OTP 1 still be valid?

This is a security-critical decision. Accepting OTP 1 after OTP 2 is issued means:
- An attacker who intercepted OTP 1 can still use it even after the user has "moved on"
- The concept of a "resend" is meaningless if old tokens remain active

### Options Considered

| Option | Behaviour | Security | User Experience |
|---|---|---|---|
| A | Both OTPs valid simultaneously | Poor — intercepted OTP 1 still works | Confusing |
| B | **Supersession: OTP 1 invalidated on OTP 2 issuance** | Strong — only latest token is valid | Clear |
| C | OTP 1 valid until natural expiry (5 min) | Moderate | Slightly more forgiving |

### Decision: Option B — Strict Supersession

When a new OTP is created (`create_and_send_otp`), all prior active OTPs are
immediately invalidated:
```python
EmailOTP.objects.filter(user=user, is_active=True).update(is_active=False)
```

The new OTP is the only valid credential. Submitting an old OTP after a resend
results in `code='otp_invalid'` ("No active OTP found").

**Test verification**: `test_otp_resend_supersession` explicitly:
1. Issues OTP 1 with a known hash
2. Resends (issues OTP 2) via the `/resend-otp/` endpoint
3. Confirms OTP 1's `is_active` is now `False`
4. Submits OTP 1's plaintext → expects rejection (400)

### Trade-off
If a mail delivery is delayed and the user clicks resend, they may receive two emails
(OTP 1 still in transit, OTP 2 freshly delivered). Only OTP 2 will work. This is
the correct and secure behaviour — it's consistent with how production systems like
GitHub, Google, and Stripe handle OTP supersession.

---

## Decision 4: Cryptographically Secure OTP Generation

### Problem
The initial implementation used `random.randint(100000, 999999)` to generate the OTP.
Python's `random` module is a Mersenne Twister — a PRNG designed for simulations, not
security. Its output can be predicted if enough previous values are observed.

### Options Considered

| Option | Module | Secure? |
|---|---|---|
| `random.randint` | stdlib `random` | ✗ Not cryptographically secure |
| **`secrets.randbelow`** | stdlib `secrets` | ✓ OS entropy source |
| `os.urandom` | stdlib | ✓ OS entropy; needs manual formatting |

### Decision: `secrets.randbelow(900000) + 100000`

```python
def generate_otp_digits() -> str:
    return str(secrets.randbelow(900000) + 100000)
```

`secrets.randbelow` uses `os.urandom` under the hood, ensuring OTPs cannot be
predicted by observing previous values. The comparison also uses `secrets.compare_digest`
to prevent timing-attack recovery of the OTP hash.

### Trade-off
None meaningful. `secrets` is part of the Python standard library since 3.6 and adds
zero dependencies.
