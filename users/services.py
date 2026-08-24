import hashlib
import secrets
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User

from common.exceptions import (
    InvalidOTPException,
    OTPExpiredException,
    OTPMaxAttemptsException,
)
from users.models import EmailOTP, UserProfile

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 3
OTP_LENGTH = 6


def generate_unique_username(email: str) -> str:
    """
    Autogenerate a clean, unique username derived from the email local-part
    plus a cryptographically random hex suffix.  The loop guarantees uniqueness
    even under high registration concurrency.
    """
    base_prefix = email.split('@')[0]
    cleaned_prefix = ''.join(c for c in base_prefix if c.isalnum()) or 'user'
    # Truncate to avoid hitting the 150-char username limit
    cleaned_prefix = cleaned_prefix[:30]

    while True:
        suffix = secrets.token_hex(4)  # 8 hex chars
        username = f"{cleaned_prefix}_{suffix}"
        if not User.objects.filter(username=username).exists():
            return username


def hash_otp(otp_str: str) -> str:
    """
    Return the SHA-256 hex digest of a plaintext OTP string.
    Plaintext is NEVER stored or logged.
    """
    return hashlib.sha256(otp_str.encode('utf-8')).hexdigest()


def generate_otp_digits() -> str:
    """
    Generate a cryptographically secure 6-digit numeric OTP.
    Uses secrets.randbelow instead of random.randint for security.
    """
    # secrets.randbelow(900000) gives [0, 900000), add 100000 for [100000, 999999]
    return str(secrets.randbelow(900000) + 100000)


def create_and_send_otp(user: User) -> EmailOTP:
    """
    Supersede all prior active OTPs for the user, create a new hashed OTP
    with a 5-minute TTL, and dispatch the plaintext code via the configured
    email backend.  The plaintext OTP is discarded immediately after dispatch.
    """
    # Single-active supersession: deactivate all existing active OTPs
    EmailOTP.objects.filter(user=user, is_active=True).update(is_active=False)

    raw_otp = generate_otp_digits()
    hashed = hash_otp(raw_otp)
    expires = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    otp_record = EmailOTP.objects.create(
        user=user,
        otp_hash=hashed,
        expires_at=expires,
        attempts_count=0,
        is_active=True,
    )

    # Dispatch via console/file backend — plaintext stays in the email transport
    # layer only, never in DB or API responses.
    send_mail(
        subject="Kroma Events — Email Verification Code",
        message=(
            f"Hello,\n\n"
            f"Your verification code is: {raw_otp}\n\n"
            f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n"
            f"If you did not request this, please ignore this email.\n\n"
            f"— Kroma Events Team"
        ),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kromaevents.com'),
        recipient_list=[user.email],
        fail_silently=False,
    )

    return otp_record


def verify_user_otp(user: User, submitted_otp: str) -> bool:
    """
    Validate a user-submitted OTP code against the latest active OTP record.

    Enforces:
      - Active-OTP existence check
      - 5-minute expiry (TTL)
      - Maximum 3 failed attempts before permanent invalidation
      - Constant-time hash comparison via `secrets.compare_digest`

    On success, marks the OTP inactive and sets `UserProfile.is_verified = True`.
    """
    active_otp = (
        EmailOTP.objects
        .filter(user=user, is_active=True)
        .order_by('-created_at')
        .first()
    )

    if not active_otp:
        raise InvalidOTPException(
            detail="No active OTP found. Please request a new OTP.",
            code="otp_invalid",
        )

    # --- Expiry check ---
    if active_otp.expires_at < timezone.now():
        active_otp.is_active = False
        active_otp.save(update_fields=['is_active'])
        raise OTPExpiredException()

    # --- Attempt-limit check (pre-validation) ---
    if active_otp.attempts_count >= OTP_MAX_ATTEMPTS:
        active_otp.is_active = False
        active_otp.save(update_fields=['is_active'])
        raise OTPMaxAttemptsException()

    # --- Hash comparison (constant-time to prevent timing attacks) ---
    submitted_hash = hash_otp(submitted_otp.strip())
    hashes_match = secrets.compare_digest(submitted_hash, active_otp.otp_hash)

    if not hashes_match:
        active_otp.attempts_count += 1
        if active_otp.attempts_count >= OTP_MAX_ATTEMPTS:
            active_otp.is_active = False
            active_otp.save(update_fields=['attempts_count', 'is_active'])
            raise OTPMaxAttemptsException()
        else:
            active_otp.save(update_fields=['attempts_count'])
            remaining = OTP_MAX_ATTEMPTS - active_otp.attempts_count
            raise InvalidOTPException(
                detail=f"Invalid OTP code. {remaining} attempt(s) remaining.",
                code="otp_invalid",
            )

    # --- Success: consume the OTP and verify the account ---
    active_otp.is_active = False
    active_otp.save(update_fields=['is_active'])

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.is_verified = True
    profile.save(update_fields=['is_verified'])

    return True
