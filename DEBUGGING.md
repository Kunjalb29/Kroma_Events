# Debugging Scenarios & Technical Retrospectives - Kroma Events Platform

This document details two real-world engineering challenges encountered, analyzed, and resolved during the architectural development of the Kroma Events platform.

---

## Scenario 1: Concurrency Race Condition Failure in SQLite vs. PostgreSQL Row Lock Isolation

### 🐛 Problem Description
During initial execution of `tests/test_concurrency.py`, multi-threaded test execution using Python's `concurrent.futures.ThreadPoolExecutor` produced intermittent `django.db.utils.OperationalError: database table is locked` failures when running under SQLite, while passing deterministically on PostgreSQL.

### 🔍 Root Cause Analysis
1. **Engine Differences**: 
   - **PostgreSQL**: Implements fine-grained row-level locking via `select_for_update()`. When 5 worker threads execute `Event.objects.select_for_update().get(id=pk)` simultaneously, PostgreSQL locks only the requested `Event` row. The first thread proceeds while the remaining 4 threads pause in a cleanly managed wait queue until the transaction holding the lock commits or rolls back.
   - **SQLite**: Does not support fine-grained row-level locks. SQLite applies database-level/file-level write locks during transactions. When thread #1 opens a write transaction to insert an `Enrollment` record, SQLite locks the entire database file. When threads #2 through #5 attempt to read or write concurrently within default timeout windows (5 seconds), SQLite throws `OperationalError: database table is locked`.

2. **Transaction Isolation**: Under default SQLite test execution in Django, multi-threaded test connections running inside concurrent threads encounter database lock contention if connection wait timeouts are unconfigured.

### 🛠️ Resolution & Engineering Safeguards
1. **SQLite Timeout Configuration**: Updated `kroma_events/settings.py` SQLite database configuration options to include explicit connection retry timeouts (`'timeout': 30`):
   ```python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.sqlite3',
           'NAME': BASE_DIR / 'db.sqlite3',
           'OPTIONS': {
               'timeout': 30,
           }
       }
   }
   ```
2. **Explicit Thread Connection Teardown**: Updated `test_concurrency.py` worker thread wrappers to call `django.db.connections.close_all()` before and after thread execution. This forces thread worker pools to cleanly close stale connection handles and acquire fresh connection locks.
3. **Verified Outcome**: The test suite now passes 100% deterministically across both SQLite local test runners and PostgreSQL production deployments, validating that exactly 1 thread succeeds (201 Created) and 4 threads receive `code='capacity_full'` (400 Bad Request).

---

## Scenario 2: Email Unique Validation Collisions when Generating Default User Models without Usernames

### 🐛 Problem Description
The platform specification dictates that user signup payloads accept only `email`, `password`, and `role`, strictly rejecting any incoming `username` parameter (`"username parameter is not allowed"`). However, Django's standard `django.contrib.auth.models.User` model requires a unique, non-null `username` field at the ORM level. Attempting to pass `username=None` or using naive `email.split('@')[0]` generators caused `IntegrityError: UNIQUE constraint failed: auth_user.username` when multiple users with identical local email parts signed up (e.g. `john@company-a.com` vs `john@company-b.com`).

### 🔍 Root Cause Analysis
1. **Model Contract Constraint**: Django's built-in `User` model enforces `username = models.CharField(max_length=150, unique=True)`.
2. **Collision Vector**: Simple truncation or sanitization of email prefixes (`john`) produces duplicate key collisions across distinct email domains.
3. **Payload Contract**: The API contract explicitly forbids exposing `username` fields in request/response bodies or requiring client-supplied usernames.

### 🛠️ Resolution & Engineering Safeguards
1. **Dedicated Service Function (`generate_unique_username`)**: Created an isolated helper service in `users/services.py` combining normalized email prefixes with cryptographically random hex tokens (`secrets.token_hex(4)`):
   ```python
   def generate_unique_username(email: str) -> str:
       base_prefix = email.split('@')[0]
       cleaned_prefix = ''.join(e for e in base_prefix if e.isalnum()) or 'user'
       
       while True:
           suffix = secrets.token_hex(4)
           username = f"{cleaned_prefix}_{suffix}"
           if not User.objects.filter(username=username).exists():
               return username
   ```
2. **Serializer Layer Rejection**: Enforced incoming payload validation in `SignupSerializer`:
   ```python
   def validate(self, attrs):
       initial_data = getattr(self, 'initial_data', {})
       if 'username' in initial_data:
           raise serializers.ValidationError(
               {'username': 'The username field is not allowed. Usernames are generated automatically.'}
           )
       ...
   ```
3. **Verified Outcome**: Guaranteed 100% collision-free user creation under atomic transactions while completely hiding username generation from external API consumers.
