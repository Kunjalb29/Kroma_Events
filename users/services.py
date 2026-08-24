import hashlib
import random
import secrets
import uuid
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
from users.models import EmailOTP, UserProfile, UserRole

def generate_unique_username(email: str) -> str:
    """
    Autogenerate clean unique username derived from email and random token.
    """
    base_prefix = email.split('@')[0]
    cleaned_prefix = ''.join(e for e in base_prefix if e.isalnum()) or 'user'
    
    while True:
        suffix = secrets.token_hex(4)
        username = f"{cleaned_prefix}_{suffix}"
        if not User.objects.filter(username=username).exists():
            return username

def hash_otp(otp_str: str) -> str:
    """
    Returns SHA-256 hash of plaintext OTP.
    """
    return hashlib.sha256(otp_str.encode('utf-8')).hexdigest()

def generate_otp_digits() -> str:
    """
    Generate 6-digit numeric OTP string.
    """
    return f"{random.randint(100000, 999999)}"

def create_and_send_otp(user: User) -> EmailOTP:
    """
    Invalidates any existing active OTPs for user, creates new hashed OTP with 5 min TTL,
    and sends plaintext OTP via email console backend (never returned or logged elsewhere).
    """
    # Supersede/invalidate prior active OTPs
    EmailOTP.objects.filter(user=user, is_active=True).update(is_active=False)

    raw_otp = generate_otp_digits()
    hashed = hash_otp(raw_otp)
    expires = timezone.now() + timedelta(minutes=5)

    otp_record = EmailOTP.objects.create(
        user=user,
        otp_hash=hashed,
        expires_at=expires,
        attempts_count=0,
        is_active=True
    )

    # Send via console/file email backend
    send_mail(
        subject="Kroma Events - Verification OTP",
        message=f"Your verification code is: {raw_otp}. It expires in 5 minutes.",
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kromaevents.com'),
        recipient_list=[user.email],
        fail_silently=False,
    )

    return otp_record

def verify_user_otp(user: User, submitted_otp: str) -> bool:
    """
    Verifies user-provided OTP code. Enforces active status, expiration (5 min TTL),
    and maximum 3 failed attempts lockout before invalidation.
    """
    active_otp = EmailOTP.objects.filter(user=user, is_active=True).order_by('-created_at').first()

    if not active_otp:
        raise InvalidOTPException(detail="No active OTP found. Please request a new OTP.", code="otp_invalid")

    # Check expiration
    if active_otp.expires_at < timezone.now():
        active_otp.is_active = False
        active_otp.save(update_fields=['is_active'])
        raise OTPExpiredException()

    # Check attempt limit
    if active_otp.attempts_count >= 3:
        active_otp.is_active = False
        active_otp.save(update_fields=['is_active'])
        raise OTPMaxAttemptsException()

    # Validate OTP hash
    submitted_hash = hash_otp(submitted_otp.strip())
    if submitted_hash != active_otp.otp_hash:
        active_otp.attempts_count += 1
        if active_otp.attempts_count >= 3:
            active_otp.is_active = False
            active_otp.save(update_fields=['attempts_count', 'is_active'])
            raise OTPMaxAttemptsException()
        else:
            active_otp.save(update_fields=['attempts_count'])
            raise InvalidOTPException(detail=f"Invalid OTP code. {3 - active_otp.attempts_count} attempt(s) remaining.", code="otp_invalid")

    # OTP is valid!
    active_otp.is_active = False
    active_otp.save(update_fields=['is_active'])

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.is_verified = True
    profile.save(update_fields=['is_verified'])

    return True
