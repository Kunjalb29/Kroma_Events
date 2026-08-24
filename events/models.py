from django.db import models
from django.contrib.auth.models import User


class EnrollmentStatus(models.TextChoices):
    ENROLLED = 'ENROLLED', 'Enrolled'
    CANCELED = 'CANCELED', 'Canceled'


class Event(models.Model):
    """
    Represents an event created by a Facilitator.

    Indexes on starts_at, language, and location support fast discovery queries.
    The `enrolled_count` and `available_seats` properties are usable directly
    on model instances; the serializer annotates these on querysets for
    efficiency.
    """
    title = models.CharField(max_length=255)
    description = models.TextField()
    language = models.CharField(max_length=50, db_index=True)
    location = models.CharField(max_length=255, db_index=True)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of seats. Leave blank for unlimited capacity.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_events',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['starts_at']
        verbose_name = 'Event'
        verbose_name_plural = 'Events'
        indexes = [
            models.Index(fields=['starts_at'], name='event_starts_at_idx'),
            models.Index(fields=['language'], name='event_language_idx'),
            models.Index(fields=['location'], name='event_location_idx'),
        ]

    def __str__(self):
        return f"{self.title} @ {self.starts_at.strftime('%Y-%m-%d %H:%M UTC')}"

    @property
    def enrolled_count(self) -> int:
        """Number of currently active (ENROLLED) enrollments for this event."""
        return self.enrollments.filter(status=EnrollmentStatus.ENROLLED).count()

    @property
    def available_seats(self):
        """
        Remaining seats. Returns None if the event has unlimited capacity.
        Always returns 0 if the event is over-capacity (defensive).
        """
        if self.capacity is None:
            return None
        return max(0, self.capacity - self.enrolled_count)


class Enrollment(models.Model):
    """
    Records a Seeker's enrollment in an Event.

    State machine:
        ENROLLED ──► CANCELED ──► ENROLLED  (re-enrollment, if capacity permits)

    Constraint:
        A partial unique index on (event, seeker) WHERE status = 'ENROLLED'
        ensures a seeker can hold at most one *active* enrollment per event,
        while preserving historical CANCELED rows for audit purposes.
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='enrollments')
    seeker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    status = models.CharField(
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ENROLLED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Enrollment'
        verbose_name_plural = 'Enrollments'
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'seeker'],
                condition=models.Q(status='ENROLLED'),
                name='unique_active_enrollment_per_seeker',
            )
        ]

    def __str__(self):
        return f"{self.seeker.email} → {self.event.title} [{self.status}]"
