"""
management/commands/seed_data.py
─────────────────────────────────
Seed sample data to make evaluation / manual testing easy.

Usage:
    python manage.py seed_data

Creates:
    - 1 Facilitator account  (facilitator@kroma.dev / Pass1234!)
    - 2 Seeker accounts      (seeker1@kroma.dev, seeker2@kroma.dev / Pass1234!)
    - 3 upcoming Events
    - All profiles set is_verified=True so you can log in immediately.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from users.models import UserProfile, UserRole
from events.models import Event, Enrollment, EnrollmentStatus


FACILITATOR_EMAIL = "facilitator@kroma.dev"
SEEKER1_EMAIL = "seeker1@kroma.dev"
SEEKER2_EMAIL = "seeker2@kroma.dev"
PASSWORD = "Pass1234!"


class Command(BaseCommand):
    help = "Seed sample evaluation data (facilitator, seekers, events)."

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding data...")

        # --- Facilitator ---
        facilitator, created = User.objects.get_or_create(
            email=FACILITATOR_EMAIL,
            defaults={"username": "facilitator_kroma"},
        )
        if created or not hasattr(facilitator, 'profile'):
            facilitator.set_password(PASSWORD)
            facilitator.save()
        UserProfile.objects.update_or_create(
            user=facilitator,
            defaults={"role": UserRole.FACILITATOR, "is_verified": True},
        )
        self.stdout.write(f"  ✓ Facilitator: {FACILITATOR_EMAIL} / {PASSWORD}")

        # --- Seekers ---
        for i, email in enumerate([SEEKER1_EMAIL, SEEKER2_EMAIL], start=1):
            seeker, created = User.objects.get_or_create(
                email=email,
                defaults={"username": f"seeker{i}_kroma"},
            )
            if created:
                seeker.set_password(PASSWORD)
                seeker.save()
            UserProfile.objects.update_or_create(
                user=seeker,
                defaults={"role": UserRole.SEEKER, "is_verified": True},
            )
            self.stdout.write(f"  ✓ Seeker:      {email} / {PASSWORD}")

        # --- Events ---
        now = timezone.now()
        events_data = [
            {
                "title": "Django REST Mastery Workshop",
                "description": "Deep dive into DRF serializers, viewsets, and authentication patterns.",
                "language": "English",
                "location": "Online - Zoom",
                "starts_at": now + timedelta(days=3),
                "ends_at": now + timedelta(days=3, hours=3),
                "capacity": 30,
            },
            {
                "title": "PostgreSQL Concurrency & Locking",
                "description": "SELECT FOR UPDATE, MVCC, deadlock avoidance, and row-level locking.",
                "language": "English",
                "location": "Bangalore, India",
                "starts_at": now + timedelta(days=7),
                "ends_at": now + timedelta(days=7, hours=2),
                "capacity": 10,
            },
            {
                "title": "Python Security Best Practices",
                "description": "OTP design, secrets module, timing-safe comparisons, and hashing.",
                "language": "Python",
                "location": "Online - Google Meet",
                "starts_at": now + timedelta(days=14),
                "ends_at": now + timedelta(days=14, hours=4),
                "capacity": None,  # unlimited
            },
        ]

        for data in events_data:
            event, created = Event.objects.get_or_create(
                title=data["title"],
                defaults={**data, "created_by": facilitator},
            )
            action = "Created" if created else "Already exists"
            self.stdout.write(f"  ✓ Event:       {action} — {event.title}")

        self.stdout.write(self.style.SUCCESS("\nSeed complete. Login credentials printed above."))
