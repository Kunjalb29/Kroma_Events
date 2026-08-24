from django.db import models
from django.contrib.auth.models import User

class UserRole(models.TextChoices):
    SEEKER = 'SEEKER', 'Seeker'
    FACILITATOR = 'FACILITATOR', 'Facilitator'

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.SEEKER)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.role} (Verified: {self.is_verified})"

class EmailOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    otp_hash = models.CharField(max_length=64)  # SHA-256 string
    expires_at = models.DateTimeField()
    attempts_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP for {self.user.email} (Active: {self.is_active})"
