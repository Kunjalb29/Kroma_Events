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
            username='facil_1',
            email='facilitator1@example.com',
            password='Password123!'
        )
        UserProfile.objects.create(user=user, role=UserRole.FACILITATOR, is_verified=True)
        return user

    @pytest.fixture
    def seeker(self):
        user = User.objects.create_user(
            username='seeker_1',
            email='seeker1@example.com',
            password='Password123!'
        )
        UserProfile.objects.create(user=user, role=UserRole.SEEKER, is_verified=True)
        return user

    @pytest.fixture
    def event(self, facilitator):
        now = timezone.now()
        return Event.objects.create(
            title='Python Workshop 2026',
            description='Advanced Django Engineering',
            language='Python',
            location='Online',
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=2, hours=3),
            capacity=2,
            created_by=facilitator
        )

    def test_enrollment_cancellation_reenrollment_lifecycle(self, seeker, event):
        client = APIClient()
        client.force_authenticate(user=seeker)

        # 1. Initial Enrollment
        res_enroll = client.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_enroll.status_code == 201
        assert res_enroll.data['enrollment']['status'] == EnrollmentStatus.ENROLLED

        assert event.enrolled_count == 1
        assert event.available_seats == 1

        # 2. Cancellation
        res_cancel = client.post(f'/api/v1/events/{event.id}/cancel/')
        assert res_cancel.status_code == 200
        assert res_cancel.data['enrollment']['status'] == EnrollmentStatus.CANCELED

        assert event.enrolled_count == 0
        assert event.available_seats == 2

        # 3. Re-enrollment
        res_reenroll = client.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_reenroll.status_code == 201
        assert res_reenroll.data['enrollment']['status'] == EnrollmentStatus.ENROLLED

        assert event.enrolled_count == 1
        assert event.available_seats == 1

        # Verify only 1 active enrollment record exists
        active_enrollments = Enrollment.objects.filter(event=event, seeker=seeker, status=EnrollmentStatus.ENROLLED)
        assert active_enrollments.count() == 1

    def test_partial_unique_constraint_enforcement(self, seeker, event):
        client = APIClient()
        client.force_authenticate(user=seeker)

        # First enrollment
        client.post(f'/api/v1/events/{event.id}/enroll/')

        # Duplicate active enrollment attempt
        res_dup = client.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_dup.status_code == 400
        assert res_dup.data['code'] == 'already_enrolled'

    def test_capacity_reclaim_on_cancellation(self, facilitator, seeker, event):
        # Create second seeker
        seeker2 = User.objects.create_user(username='seeker_2', email='seeker2@example.com', password='Password123!')
        UserProfile.objects.create(user=seeker2, role=UserRole.SEEKER, is_verified=True)

        # Fill capacity = 2
        Enrollment.objects.create(event=event, seeker=seeker, status=EnrollmentStatus.ENROLLED)
        Enrollment.objects.create(event=event, seeker=seeker2, status=EnrollmentStatus.ENROLLED)

        assert event.enrolled_count == 2
        assert event.available_seats == 0

        # Create third seeker
        seeker3 = User.objects.create_user(username='seeker_3', email='seeker3@example.com', password='Password123!')
        UserProfile.objects.create(user=seeker3, role=UserRole.SEEKER, is_verified=True)

        client3 = APIClient()
        client3.force_authenticate(user=seeker3)

        # Seeker 3 attempt to enroll when full
        res_full = client3.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_full.status_code == 400
        assert res_full.data['code'] == 'capacity_full'

        # Seeker 1 cancels enrollment
        client1 = APIClient()
        client1.force_authenticate(user=seeker)
        client1.post(f'/api/v1/events/{event.id}/cancel/')

        assert event.enrolled_count == 1
        assert event.available_seats == 1

        # Seeker 3 now successfully claims liberated seat
        res_claim = client3.post(f'/api/v1/events/{event.id}/enroll/')
        assert res_claim.status_code == 201
        assert event.enrolled_count == 2
