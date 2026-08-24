import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from users.models import EmailOTP, UserProfile, UserRole
from users.services import create_and_send_otp, hash_otp
from common.exceptions import (
    InvalidOTPException,
    OTPExpiredException,
    OTPMaxAttemptsException,
)

@pytest.mark.django_db
class TestOTPLifecycle:

    @pytest.fixture
    def unverified_user(self):
        user = User.objects.create_user(
            username='test_seeker_1',
            email='seeker1@example.com',
            password='Password123!',
            is_active=True
        )
        UserProfile.objects.create(
            user=user,
            role=UserRole.SEEKER,
            is_verified=False
        )
        return user

    def test_otp_generation_and_hashing(self, unverified_user):
        otp_record = create_and_send_otp(unverified_user)
        assert otp_record.is_active is True
        assert otp_record.attempts_count == 0
        assert len(otp_record.otp_hash) == 64  # SHA-256 hex length
        assert otp_record.expires_at > timezone.now()

    def test_otp_verification_success(self, unverified_user):
        otp_record = create_and_send_otp(unverified_user)
        client = APIClient()
        
        # We extract plaintext OTP by overriding hash check in service test or via helper
        raw_otp = '123456'
        otp_record.otp_hash = hash_otp(raw_otp)
        otp_record.save(update_fields=['otp_hash'])

        response = client.post('/api/v1/auth/verify-otp/', {
            'email': unverified_user.email,
            'otp': raw_otp
        }, format='json')

        assert response.status_code == 200
        assert response.data['is_verified'] is True

        unverified_user.profile.refresh_from_db()
        assert unverified_user.profile.is_verified is True

        otp_record.refresh_from_db()
        assert otp_record.is_active is False

    def test_otp_expiration_ttl(self, unverified_user):
        otp_record = create_and_send_otp(unverified_user)
        raw_otp = '123456'
        otp_record.otp_hash = hash_otp(raw_otp)
        # Expire the OTP (set 6 minutes in past)
        otp_record.expires_at = timezone.now() - timedelta(minutes=6)
        otp_record.save(update_fields=['expires_at', 'otp_hash'])

        client = APIClient()
        response = client.post('/api/v1/auth/verify-otp/', {
            'email': unverified_user.email,
            'otp': raw_otp
        }, format='json')

        assert response.status_code == 400
        assert response.data['code'] == 'otp_expired'

        otp_record.refresh_from_db()
        assert otp_record.is_active is False

    def test_otp_max_3_attempts_lockout(self, unverified_user):
        otp_record = create_and_send_otp(unverified_user)
        raw_otp = '123456'
        wrong_otp = '999999'
        otp_record.otp_hash = hash_otp(raw_otp)
        otp_record.save(update_fields=['otp_hash'])

        client = APIClient()

        # Attempt 1 (wrong)
        res1 = client.post('/api/v1/auth/verify-otp/', {'email': unverified_user.email, 'otp': wrong_otp}, format='json')
        assert res1.status_code == 400
        assert res1.data['code'] == 'otp_invalid'

        # Attempt 2 (wrong)
        res2 = client.post('/api/v1/auth/verify-otp/', {'email': unverified_user.email, 'otp': wrong_otp}, format='json')
        assert res2.status_code == 400
        assert res2.data['code'] == 'otp_invalid'

        # Attempt 3 (wrong - triggers lockout)
        res3 = client.post('/api/v1/auth/verify-otp/', {'email': unverified_user.email, 'otp': wrong_otp}, format='json')
        assert res3.status_code == 400
        assert res3.data['code'] == 'otp_max_attempts_exceeded'

        otp_record.refresh_from_db()
        assert otp_record.is_active is False
        assert otp_record.attempts_count >= 3

    def test_otp_resend_supersession(self, unverified_user):
        otp1 = create_and_send_otp(unverified_user)
        assert otp1.is_active is True

        # Resend OTP
        client = APIClient()
        response = client.post('/api/v1/auth/resend-otp/', {'email': unverified_user.email}, format='json')
        assert response.status_code == 200

        otp1.refresh_from_db()
        assert otp1.is_active is False  # OTP 1 invalidated/superseded

        active_otps = EmailOTP.objects.filter(user=unverified_user, is_active=True)
        assert active_otps.count() == 1
        assert active_otps.first().id != otp1.id
