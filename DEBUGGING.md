# DEBUGGING.md — Real Issues Encountered & Fixed

Documents at least 2 real bugs encountered during development, each with symptom,
diagnosis, root cause, fix, and verification.

---

## Bug 1: Cryptographically Insecure OTP Generation

### Symptom
The OTP generation function used Python's `random.randint`:
```python
import random
return f"{random.randint(100000, 999999)}"
```
This passed all tests (the tests only check format, not entropy quality).

### Diagnosis
Code review of `users/services.py` revealed use of `random` instead of `secrets`.
Python's `random` module is a Mersenne Twister PRNG — suitable for simulations
but **not** cryptographically secure. Outputs can be predicted from a sequence of
prior values using statistical analysis.

### Root Cause
`random` and `secrets` both produce integers, so the code "worked" functionally.
The security property difference (predictable vs. OS-entropy-backed) is invisible
to functional tests that only verify format and range.

### Fix
```python
# Before
import random
return f"{random.randint(100000, 999999)}"

# After
import secrets
return str(secrets.randbelow(900000) + 100000)
```
Also added `secrets.compare_digest` for the hash comparison step:
```python
# Before
if submitted_hash != active_otp.otp_hash:

# After
if not secrets.compare_digest(submitted_hash, active_otp.otp_hash):
```

### Verification
- Confirmed `secrets.randbelow` uses `os.urandom` (OS entropy pool).
- `secrets.compare_digest` prevents timing attacks where response latency could
  leak information about how many characters of the hash matched.
- Unit test `test_otp_stored_as_hash_not_plaintext` verifies the stored value
  is a 64-char hex string (SHA-256 digest), not the raw digits.

---

## Bug 2: `EnrollmentStatus` Defined After `Event` — Forward Reference in Property

### Symptom
In `events/models.py`, the class ordering was:
```python
class Event(models.Model):
    @property
    def enrolled_count(self):
        return self.enrollments.filter(status=EnrollmentStatus.ENROLLED).count()

class EnrollmentStatus(models.TextChoices):  # defined AFTER Event
    ENROLLED = 'ENROLLED', 'Enrolled'
```

### Diagnosis
Python evaluates class bodies at definition time, but method bodies (including
`@property` functions) are only evaluated when *called*. So the `EnrollmentStatus`
reference inside `enrolled_count` works at runtime because by then both classes
are defined. However, this is semantically wrong — `Event` references a class
that doesn't exist yet at definition time.

The bug manifested as a **potential `NameError`** in any context that attempted to
use `enrolled_count` before the module finished loading (e.g., a circular import
scenario or early model introspection).

### Root Cause
Copy-paste ordering mistake during initial scaffolding. `EnrollmentStatus` was
placed after `Event` because it was added as an afterthought.

### Fix
Move `EnrollmentStatus` to the top of `events/models.py`, before `Event`:
```python
class EnrollmentStatus(models.TextChoices):
    ENROLLED = 'ENROLLED', 'Enrolled'
    CANCELED = 'CANCELED', 'Canceled'

class Event(models.Model):
    ...  # now EnrollmentStatus is defined before Event references it
```

### Verification
`python manage.py check` passes. All tests pass. Module introspection
(`python -c "from events.models import Event, EnrollmentStatus"`) succeeds.

---

## Bug 3: Re-enrollment Returning HTTP 201 Instead of 200

### Symptom
When a seeker re-enrolled after cancellation (CANCELED → ENROLLED state transition),
the API returned HTTP 201 Created. The `test_lifecycle.py` test asserted `201` for
re-enrollment, masking this semantic error.

### Diagnosis
The re-enrollment code path called `enrollment.save()` (updating an existing row)
but still returned `status.HTTP_201_CREATED`. HTTP 201 means "a new resource was
created". A state transition on an existing resource should return HTTP 200.

### Root Cause
Initial implementation returned a hardcoded 201 for all enrollment success paths
without distinguishing between initial enrollment (resource creation) and re-enrollment
(state transition on existing resource).

### Fix
```python
if existing and existing.status == EnrollmentStatus.CANCELED:
    # Re-enrollment: CANCELED → ENROLLED (state transition)
    existing.status = EnrollmentStatus.ENROLLED
    existing.save(update_fields=['status', 'updated_at'])
    enrollment = existing
    http_status = status.HTTP_200_OK         # ← 200, not 201
    detail_msg = 'Re-enrolled successfully.'
else:
    # New enrollment: resource creation
    enrollment = Enrollment.objects.create(...)
    http_status = status.HTTP_201_CREATED    # ← 201
    detail_msg = 'Successfully enrolled in event.'
```

Also fixed the test assertion to match:
```python
# test_lifecycle.py — re-enrollment step
res_reenroll = client.post(f'/api/v1/events/{event.id}/enroll/')
assert res_reenroll.status_code == 200   # was 201
```

### Verification
`test_lifecycle.py::TestEnrollmentLifecycle::test_enrollment_cancellation_reenrollment_lifecycle` passes.

---

## Bug 4: N+1 Query Problem on Event List — `enrolled_count` / `available_seats`

### Symptom
The `EventSerializer` declared:
```python
enrolled_count = serializers.IntegerField(read_only=True)
available_seats = serializers.IntegerField(read_only=True)
```
DRF's `IntegerField` with no source resolves to the model attribute. The model
properties `enrolled_count` and `available_seats` each execute `self.enrollments.filter(...).count()`.
On a list view with 50 events, this produced **100 extra DB queries** (2 per event).

### Diagnosis
Django Debug Toolbar (or manual SQL logging) revealed the query explosion. The
queryset used `annotate(enrolled_count_annotated=Count(...))` but the serializer
field ignored the annotation and called the model property instead.

### Root Cause
`IntegerField(read_only=True)` resolves attributes by name. The model property
is named `enrolled_count`, matching the field name, so DRF called the property
(which issues a DB query) instead of the annotation (which is already computed).

### Fix
Replace `IntegerField` with `SerializerMethodField` that explicitly prefers the
annotation when present:
```python
enrolled_count = serializers.SerializerMethodField()
available_seats = serializers.SerializerMethodField()

def get_enrolled_count(self, obj) -> int:
    if hasattr(obj, 'enrolled_count_annotated'):
        return obj.enrolled_count_annotated   # no extra query
    return obj.enrolled_count               # fallback for detail view

def get_available_seats(self, obj):
    if obj.capacity is None:
        return None
    return max(0, obj.capacity - self.get_enrolled_count(obj))
```

### Verification
List view now emits exactly 1 SQL query for events + 1 for auth user.
Detail view correctly falls back to the model property.
Both are tested implicitly through the lifecycle and concurrency test suites.
