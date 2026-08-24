from django.db import models
from django.contrib.auth.models import User

class Event(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    language = models.CharField(max_length=50, db_index=True)
    location = models.CharField(max_length=255, db_index=True)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_events')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['starts_at']
        indexes = [
            models.Index(fields=['starts_at']),
            models.Index(fields=['language']),
            models.Index(fields=['location']),
        ]

    def __str__(self):
        return f"{self.title} ({self.starts_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def enrolled_count(self):
        return self.enrollments.filter(status=EnrollmentStatus.ENROLLED).count()

    @property
    def available_seats(self):
        if self.capacity is None:
            return None
        return max(0, self.capacity - self.enrolled_count)

class EnrollmentStatus(models.TextChoices):
    ENROLLED = 'ENROLLED', 'Enrolled'
    CANCELED = 'CANCELED', 'Canceled'

class Enrollment(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='enrollments')
    seeker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    status = models.CharField(
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ENROLLED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'seeker'],
                condition=models.Q(status='ENROLLED'),
                name='unique_active_enrollment_per_seeker'
            )
        ]

    def __str__(self):
        return f"{self.seeker.email} -> {self.event.title} [{self.status}]"
