import pytest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from django.db import connections
from rest_framework.test import APIClient

from users.models import UserProfile, UserRole
from events.models import Event, Enrollment, EnrollmentStatus

@pytest.mark.django_db(transaction=True)
class TestEnrollmentConcurrency:

    def test_concurrent_enrollments_capacity_limit(self):
        # 1. Setup Facilitator & Event with capacity = 10
        facilitator = User.objects.create_user(
            username='concur_facil',
            email='concur_facil@example.com',
            password='Password123!'
        )
        UserProfile.objects.create(user=facilitator, role=UserRole.FACILITATOR, is_verified=True)

        now = timezone.now()
        event = Event.objects.create(
            title='Concurrency Load Test Summit',
            description='Testing race conditions under high load',
            language='English',
            location='Virtual',
            starts_at=now + timedelta(days=5),
            ends_at=now + timedelta(days=5, hours=2),
            capacity=10,
            created_by=facilitator
        )

        # 2. Pre-enroll 9 Seekers (Capacity remaining = 1)
        for i in range(9):
            pre_seeker = User.objects.create_user(
                username=f'pre_seeker_{i}',
                email=f'pre_seeker_{i}@example.com',
                password='Password123!'
            )
            UserProfile.objects.create(user=pre_seeker, role=UserRole.SEEKER, is_verified=True)
            Enrollment.objects.create(event=event, seeker=pre_seeker, status=EnrollmentStatus.ENROLLED)

        assert event.enrolled_count == 9
        assert event.available_seats == 1

        # 3. Create 5 candidate Seekers competing for the single remaining seat
        candidate_seekers = []
        for i in range(5):
            candidate = User.objects.create_user(
                username=f'candidate_seeker_{i}',
                email=f'candidate_seeker_{i}@example.com',
                password='Password123!'
            )
            UserProfile.objects.create(user=candidate, role=UserRole.SEEKER, is_verified=True)
            candidate_seekers.append(candidate)

        # 4. Helper for multi-threaded enrollment execution
        def run_enrollment_in_thread(seeker_user):
            # Ensure fresh DB connection for worker thread
            connections.close_all()
            client = APIClient()
            client.force_authenticate(user=seeker_user)
            response = client.post(f'/api/v1/events/{event.id}/enroll/', format='json')
            connections.close_all()
            return response.status_code, response.data

        # 5. Execute 5 concurrent enrollments using ThreadPoolExecutor
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(run_enrollment_in_thread, seeker)
                for seeker in candidate_seekers
            ]
            for future in futures:
                results.append(future.result())

        # 6. Analyze and verify results
        successes = [r for r in results if r[0] == 201]
        capacity_failures = [r for r in results if r[0] == 400 and r[1].get('code') == 'capacity_full']

        assert len(successes) == 1, f"Expected exactly 1 successful enrollment, got {len(successes)}. Results: {results}"
        assert len(capacity_failures) == 4, f"Expected exactly 4 capacity full failures, got {len(capacity_failures)}. Results: {results}"

        # 7. Final DB Assertion: Total enrolled count must be strictly equal to capacity (10)
        final_enrolled_count = Enrollment.objects.filter(event_id=event.id, status=EnrollmentStatus.ENROLLED).count()
        assert final_enrolled_count == 10
