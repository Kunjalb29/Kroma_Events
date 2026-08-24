"""
tests/test_lifecycle.py
───────────────────────
Tests for the Enrollment state machine:
  ENROLLED ──► CANCELED ──► ENROLLED (re-enrollment)

Validates:
  - Happy-path enroll / cancel / re-enroll lifecycle
  - Partial unique constraint: duplicate active enrollment rejected
  - Capacity enforcement and reclamation after cancellation
"""
import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from users.models import UserProfile, UserRole
from events.models import Event, Enrollment, EnrollmentStatus


@pytest.mark.django_db
class TestEnrollmentLifecycle:

    @pytest.fixture
    def facilitator(self):
        user = User.objects.create_user(
            username='facil_lifecycle',
            email='facilitator_lc@example.com',
            password='Password123!',
        )
        UserProfile.objects.create(user=user, role=UserRole.FACILITATOR, is_verified=True)
        return user

    @pytest.fixture
    def seeker(self):
        user = User.objects.create_user(
            username='seeker_lifecycle',
            email='seeker_lc@example.com',
            password='Password123!',
        )
        UserProfile.objects.create(user=user, role=UserRole.SEEKER, is_verified=True)
        return user

    @pytest.fixture
    def event(self, facilitator):
        now = timezone.now()
        return Event.objects.create(
            title='Lifecycle Test Workshop',
            description='Advanced Django Engineering Lifecycle',
            language='Python',
            location='Online',
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=2, hours=3),
            capacity=2,
            created_by=facilitator,
        )

    # ─── Test 1: Full enroll → cancel → re-enroll cycle ─────────────────────

    def test_enrollment_cancellation_reenrollment_lifecycle(self, seeker, event):
        client = APIClient()
        client.force_authenticate(user=seeker)

        # 1. Initial Enrollment → 201 Created
        res_enroll = client.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_enroll.status_code == 201, res_enroll.data
        assert res_enroll.data['enrollment']['status'] == EnrollmentStatus.ENROLLED

        # Verify DB state
        assert event.enrolled_count == 1
        assert event.available_seats == 1

        # 2. Cancellation → 200 OK
        res_cancel = client.post(f'/api/v1/events/{event.id}/cancel/')
        assert res_cancel.status_code == 200, res_cancel.data
        assert res_cancel.data['enrollment']['status'] == EnrollmentStatus.CANCELED

        assert event.enrolled_count == 0
        assert event.available_seats == 2

        # 3. Re-enrollment → 200 OK (state transition, not resource creation)
        res_reenroll = client.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_reenroll.status_code == 200, res_reenroll.data
        assert res_reenroll.data['enrollment']['status'] == EnrollmentStatus.ENROLLED

        assert event.enrolled_count == 1
        assert event.available_seats == 1

        # Only 1 active (ENROLLED) row should exist for this seeker on this event
        active = Enrollment.objects.filter(
            event=event, seeker=seeker, status=EnrollmentStatus.ENROLLED
        )
        assert active.count() == 1

    # ─── Test 2: Duplicate enrollment rejected ───────────────────────────────

    def test_partial_unique_constraint_enforcement(self, seeker, event):
        client = APIClient()
        client.force_authenticate(user=seeker)

        # First enrollment succeeds
        first = client.post(f'/api/v1/events/{event.id}/enroll/')
        assert first.status_code == 201, first.data

        # Second active enrollment must be rejected with 'already_enrolled'
        duplicate = client.post(f'/api/v1/events/{event.id}/enroll/')
        assert duplicate.status_code == 400
        assert duplicate.data['code'] == 'already_enrolled'

    # ─── Test 3: Seat reclaimed after cancellation ───────────────────────────

    def test_capacity_reclaim_on_cancellation(self, seeker, event):
        # Create a second seeker
        seeker2 = User.objects.create_user(
            username='seeker_lc2', email='seeker_lc2@example.com', password='Password123!'
        )
        UserProfile.objects.create(user=seeker2, role=UserRole.SEEKER, is_verified=True)

        # Fill both seats (capacity=2)
        Enrollment.objects.create(event=event, seeker=seeker, status=EnrollmentStatus.ENROLLED)
        Enrollment.objects.create(event=event, seeker=seeker2, status=EnrollmentStatus.ENROLLED)
        assert event.enrolled_count == 2
        assert event.available_seats == 0

        # Third seeker cannot enroll
        seeker3 = User.objects.create_user(
            username='seeker_lc3', email='seeker_lc3@example.com', password='Password123!'
        )
        UserProfile.objects.create(user=seeker3, role=UserRole.SEEKER, is_verified=True)
        client3 = APIClient()
        client3.force_authenticate(user=seeker3)

        res_full = client3.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_full.status_code == 400
        assert res_full.data['code'] == 'capacity_full'

        # Seeker 1 cancels → seat freed
        client1 = APIClient()
        client1.force_authenticate(user=seeker)
        cancel_res = client1.post(f'/api/v1/events/{event.id}/cancel/')
        assert cancel_res.status_code == 200

        assert event.enrolled_count == 1
        assert event.available_seats == 1

        # Seeker 3 can now claim the freed seat
        res_claim = client3.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_claim.status_code == 201
        assert event.enrolled_count == 2
        assert event.available_seats == 0
