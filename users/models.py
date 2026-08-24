from django.db import models
from django.contrib.auth.models import User


class UserRole(models.TextChoices):
    SEEKER = 'SEEKER', 'Seeker'
    FACILITATOR = 'FACILITATOR', 'Facilitator'


class UserProfile(models.Model):
    """
    Extension of Django's built-in User model.
    Stores role and email-verification status.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.SEEKER)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.email} [{self.role}] (verified={self.is_verified})"


class EmailOTP(models.Model):
    """
    Stores a hashed one-time-password for email verification.

    Security guarantees:
    - otp_hash stores only the SHA-256 digest — plaintext is NEVER persisted.
    - expires_at enforces a 5-minute TTL.
    - attempts_count enforces a 3-attempt hard lockout.
    - is_active supports single-active-token supersession on resend.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    otp_hash = models.CharField(max_length=64, help_text="SHA-256 hex digest of the plaintext OTP")
    expires_at = models.DateTimeField()
    attempts_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Email OTP'
        verbose_name_plural = 'Email OTPs'
        indexes = [
            models.Index(fields=['user', 'is_active'], name='otp_user_active_idx'),
        ]

    def __str__(self):
        return f"OTP for {self.user.email} (active={self.is_active})"
