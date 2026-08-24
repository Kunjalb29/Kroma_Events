"""
tests/test_otp.py
─────────────────
Tests for the EmailOTP lifecycle (Engineering Challenge C):

  - OTP generation stores a SHA-256 hash, not plaintext (64-char hex)
  - Successful verification marks account as is_verified=True
  - 5-minute TTL: expired OTPs are rejected with code='otp_expired'
  - 3-attempt lockout: 3rd wrong attempt invalidates OTP with
    code='otp_max_attempts_exceeded'
  - Resend supersession: old active OTP becomes inactive; only the new
    OTP is valid (OTP 1 submitted after OTP 2 is issued → rejected)
"""
import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from users.models import EmailOTP, UserProfile, UserRole
from users.services import create_and_send_otp, hash_otp


@pytest.mark.django_db
class TestOTPLifecycle:

    @pytest.fixture
    def unverified_user(self):
        user = User.objects.create_user(
            username='otp_test_user',
            email='otp_test@example.com',
            password='Password123!',
            is_active=True,
        )
        UserProfile.objects.create(user=user, role=UserRole.SEEKER, is_verified=False)
        return user

    # ─── Test 1: OTP stored as SHA-256 hash, never plaintext ─────────────────

    def test_otp_stored_as_hash_not_plaintext(self, unverified_user):
        otp_record = create_and_send_otp(unverified_user)

        assert otp_record.is_active is True
        assert otp_record.attempts_count == 0
        assert len(otp_record.otp_hash) == 64        # SHA-256 hex digest length
        assert otp_record.otp_hash.isalnum()         # hex string chars only
        assert otp_record.expires_at > timezone.now()
        # The hash must NOT be the raw OTP digits
        assert not otp_record.otp_hash.isdigit()

    # ─── Test 2: Successful verification marks account verified ───────────────

    def test_otp_verification_success(self, unverified_user):
        otp_record = create_and_send_otp(unverified_user)

        # Inject a known OTP hash so we can submit the plaintext in the test
        raw_otp = '123456'
        otp_record.otp_hash = hash_otp(raw_otp)
        otp_record.save(update_fields=['otp_hash'])

        client = APIClient()
        response = client.post('/api/v1/auth/verify-otp/', {
            'email': unverified_user.email,
            'otp': raw_otp,
        }, format='json')

        assert response.status_code == 200, response.data
        assert response.data['is_verified'] is True

        unverified_user.profile.refresh_from_db()
        assert unverified_user.profile.is_verified is True

        otp_record.refresh_from_db()
        assert otp_record.is_active is False          # OTP consumed

    # ─── Test 3: Expired OTP rejected with correct code ──────────────────────

    def test_otp_expiration_ttl(self, unverified_user):
        otp_record = create_and_send_otp(unverified_user)
        raw_otp = '123456'
        otp_record.otp_hash = hash_otp(raw_otp)
        otp_record.expires_at = timezone.now() - timedelta(minutes=6)   # 6 min past
        otp_record.save(update_fields=['otp_hash', 'expires_at'])

        client = APIClient()
        response = client.post('/api/v1/auth/verify-otp/', {
            'email': unverified_user.email,
            'otp': raw_otp,
        }, format='json')

        assert response.status_code == 400
        assert response.data['code'] == 'otp_expired'

        otp_record.refresh_from_db()
        assert otp_record.is_active is False           # Expired OTP deactivated

    # ─── Test 4: 3-attempt lockout ────────────────────────────────────────────

    def test_otp_max_3_attempts_lockout(self, unverified_user):
        otp_record = create_and_send_otp(unverified_user)
        raw_otp = '123456'
        wrong_otp = '999999'
        otp_record.otp_hash = hash_otp(raw_otp)
        otp_record.save(update_fields=['otp_hash'])

        client = APIClient()

        # Attempt 1 — wrong → otp_invalid, still active
        r1 = client.post('/api/v1/auth/verify-otp/', {
            'email': unverified_user.email, 'otp': wrong_otp
        }, format='json')
        assert r1.status_code == 400
        assert r1.data['code'] == 'otp_invalid'

        # Attempt 2 — wrong → otp_invalid, still active
        r2 = client.post('/api/v1/auth/verify-otp/', {
            'email': unverified_user.email, 'otp': wrong_otp
        }, format='json')
        assert r2.status_code == 400
        assert r2.data['code'] == 'otp_invalid'

        # Attempt 3 — wrong → lockout with otp_max_attempts_exceeded
        r3 = client.post('/api/v1/auth/verify-otp/', {
            'email': unverified_user.email, 'otp': wrong_otp
        }, format='json')
        assert r3.status_code == 400
        assert r3.data['code'] == 'otp_max_attempts_exceeded'

        otp_record.refresh_from_db()
        assert otp_record.is_active is False           # Locked out → deactivated
        assert otp_record.attempts_count >= 3

    # ─── Test 5: Resend supersession — OTP 1 invalid after OTP 2 issued ──────

    def test_otp_resend_supersession(self, unverified_user):
        """
        Engineering Challenge C core case:
        OTP 1 is issued. 30s later OTP 2 is issued (resend).
        Submitting OTP 1 after OTP 2 is issued must be rejected because
        the supersession policy deactivates OTP 1 when OTP 2 is created.
        """
        # Issue OTP 1
        otp1 = create_and_send_otp(unverified_user)
        assert otp1.is_active is True

        raw_otp1 = '111111'
        otp1.otp_hash = hash_otp(raw_otp1)
        otp1.save(update_fields=['otp_hash'])

        # Issue OTP 2 via resend endpoint (supersedes OTP 1)
        client = APIClient()
        resend_response = client.post('/api/v1/auth/resend-otp/', {
            'email': unverified_user.email
        }, format='json')
        assert resend_response.status_code == 200

        # OTP 1 must now be inactive
        otp1.refresh_from_db()
        assert otp1.is_active is False

        # Exactly 1 active OTP must exist (OTP 2)
        active_otps = EmailOTP.objects.filter(user=unverified_user, is_active=True)
        assert active_otps.count() == 1
        assert active_otps.first().id != otp1.id

        # Submitting old OTP 1 must be rejected (no active OTP matches)
        stale_attempt = client.post('/api/v1/auth/verify-otp/', {
            'email': unverified_user.email,
            'otp': raw_otp1,
        }, format='json')
        assert stale_attempt.status_code == 400
        assert stale_attempt.data['code'] in ('otp_invalid', 'otp_expired')
