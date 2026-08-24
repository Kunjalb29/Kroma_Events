"""
tests/test_concurrency.py
──────────────────────────
Engineering Challenge A: Enrollment Concurrency

Scenario:
  - Event capacity = 10
  - 9 seekers are pre-enrolled (1 seat remaining)
  - 5 candidate seekers attempt to enroll simultaneously using a
    ThreadPoolExecutor (max_workers=5)

Expected outcome:
  - Exactly 1 succeeds (HTTP 201)
  - Exactly 4 fail with HTTP 400 / code='capacity_full'
  - Final DB enrolled count == 10 (no overbooking)

Implementation:
  The EnrollEventView uses SELECT FOR UPDATE inside transaction.atomic(),
  which serialises concurrent writes at the database row level.
  SQLite is used for tests (with timeout=30 for write-lock tolerance).
  PostgreSQL provides true row-level isolation in production.
"""
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.utils import timezone
from django.contrib.auth.models import User
from django.db import connections
from rest_framework.test import APIClient

from users.models import UserProfile, UserRole
from events.models import Event, Enrollment, EnrollmentStatus


@pytest.mark.django_db(transaction=True)
class TestEnrollmentConcurrency:

    def test_concurrent_enrollments_respect_capacity(self):
        # ── Setup ────────────────────────────────────────────────────────────

        facilitator = User.objects.create_user(
            username='concur_facilitator',
            email='concur_facilitator@example.com',
            password='Password123!',
        )
        UserProfile.objects.create(
            user=facilitator, role=UserRole.FACILITATOR, is_verified=True
        )

        now = timezone.now()
        event = Event.objects.create(
            title='Concurrency Load Test Summit',
            description='Testing race conditions under concurrent enrollment pressure.',
            language='English',
            location='Virtual',
            starts_at=now + timedelta(days=5),
            ends_at=now + timedelta(days=5, hours=2),
            capacity=10,
            created_by=facilitator,
        )

        # Pre-enroll 9 seekers → 1 seat remains
        for i in range(9):
            pre_seeker = User.objects.create_user(
                username=f'pre_seeker_{i}',
                email=f'pre_seeker_{i}@concur.example.com',
                password='Password123!',
            )
            UserProfile.objects.create(
                user=pre_seeker, role=UserRole.SEEKER, is_verified=True
            )
            Enrollment.objects.create(
                event=event, seeker=pre_seeker, status=EnrollmentStatus.ENROLLED
            )

        assert event.enrolled_count == 9
        assert event.available_seats == 1

        # 5 candidate seekers competing for the single remaining seat
        candidates = []
        for i in range(5):
            c = User.objects.create_user(
                username=f'candidate_{i}',
                email=f'candidate_{i}@concur.example.com',
                password='Password123!',
            )
            UserProfile.objects.create(user=c, role=UserRole.SEEKER, is_verified=True)
            candidates.append(c)

        # ── Worker function (executed in thread pool) ─────────────────────────

        def try_enroll(seeker_user):
            """Each thread gets a fresh DB connection and API client."""
            connections.close_all()
            client = APIClient()
            client.force_authenticate(user=seeker_user)
            try:
                response = client.post(
                    f'/api/v1/events/{event.id}/enroll/', format='json'
                )
                return response.status_code, dict(response.data)
            finally:
                connections.close_all()

        # ── Execute 5 concurrent enrollments ─────────────────────────────────

        results = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(try_enroll, c) for c in candidates]
            for f in as_completed(futures):
                results.append(f.result())

        # ── Assertions ────────────────────────────────────────────────────────

        successes = [r for r in results if r[0] in (200, 201)]
        capacity_failures = [
            r for r in results
            if r[0] == 400 and r[1].get('code') == 'capacity_full'
        ]

        assert len(successes) == 1, (
            f"Expected exactly 1 successful enrollment, got {len(successes)}.\n"
            f"Results: {results}"
        )
        assert len(capacity_failures) == 4, (
            f"Expected exactly 4 capacity_full failures, got {len(capacity_failures)}.\n"
            f"Results: {results}"
        )

        # Final DB check: strictly 10 active enrollments, no overbooking
        final_count = Enrollment.objects.filter(
            event_id=event.id, status=EnrollmentStatus.ENROLLED
        ).count()
        assert final_count == 10, (
            f"Overbooking detected! Expected 10 enrolled, got {final_count}."
        )
