from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q, Count
from django.utils.dateparse import parse_datetime

from common.exceptions import (
    BaseCustomException,
    CapacityFullException,
    AlreadyEnrolledException,
    EnrollmentNotFoundException,
)
from events.models import Event, Enrollment, EnrollmentStatus
from events.serializers import EventSerializer, EnrollmentSerializer
from events.permissions import IsFacilitator, IsSeeker, IsEventOwnerOrReadOnly


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _annotated_events_qs():
    """
    Return a base queryset for Event that annotates enrolled_count so that
    the serializer can avoid per-object N+1 queries on list views.
    """
    return (
        Event.objects
        .annotate(
            enrolled_count_annotated=Count(
                'enrollments',
                filter=Q(enrollments__status=EnrollmentStatus.ENROLLED),
            )
        )
        .select_related('created_by')
        .order_by('starts_at')
    )


# ---------------------------------------------------------------------------
# Event views
# ---------------------------------------------------------------------------

class EventListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/events/  — Public list/search (paginated, upcoming-first).
    POST /api/v1/events/  — Create event (Facilitator only).

    Supported query parameters:
        q            — icontains search across title and description
        location     — icontains match on location
        language     — icontains match on language
        starts_after — ISO-8601 datetime lower bound (inclusive)
        starts_before— ISO-8601 datetime upper bound (inclusive)
    """
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = _annotated_events_qs()
        params = self.request.query_params

        q = params.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        location = params.get('location', '').strip()
        if location:
            qs = qs.filter(location__icontains=location)

        language = params.get('language', '').strip()
        if language:
            qs = qs.filter(language__icontains=language)

        starts_after = params.get('starts_after', '').strip()
        if starts_after:
            dt = parse_datetime(starts_after)
            if dt:
                qs = qs.filter(starts_at__gte=dt)

        starts_before = params.get('starts_before', '').strip()
        if starts_before:
            dt = parse_datetime(starts_before)
            if dt:
                qs = qs.filter(starts_at__lte=dt)

        return qs

    def perform_create(self, serializer):
        """Only Facilitators may create events."""
        try:
            is_facilitator = self.request.user.profile.role == 'FACILITATOR'
        except Exception:
            is_facilitator = False

        if not is_facilitator:
            raise BaseCustomException(
                detail="Only users with the FACILITATOR role can create events.",
                code="permission_denied",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        serializer.save(created_by=self.request.user)


class EventDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/events/<pk>/  — Retrieve event (authenticated users).
    PUT    /api/v1/events/<pk>/  — Full update (Facilitator + owner only).
    PATCH  /api/v1/events/<pk>/  — Partial update (Facilitator + owner only).
    DELETE /api/v1/events/<pk>/  — Delete (Facilitator + owner only).
    """
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsEventOwnerOrReadOnly]

    def get_queryset(self):
        return _annotated_events_qs()

    def perform_update(self, serializer):
        """Only the Facilitator who created the event may update it."""
        self._assert_facilitator_owner()
        serializer.save()

    def perform_destroy(self, instance):
        """Only the Facilitator who created the event may delete it."""
        self._assert_facilitator_owner()
        instance.delete()

    def _assert_facilitator_owner(self):
        try:
            is_facilitator = self.request.user.profile.role == 'FACILITATOR'
        except Exception:
            is_facilitator = False
        if not is_facilitator:
            raise BaseCustomException(
                detail="Only facilitators can modify or delete events.",
                code="permission_denied",
                status_code=status.HTTP_403_FORBIDDEN,
            )


# ---------------------------------------------------------------------------
# Enrollment views
# ---------------------------------------------------------------------------

class EnrollEventView(APIView):
    """
    POST /api/v1/events/<pk>/enroll/  — Enroll in an event (Seeker only).

    Concurrency strategy — Pessimistic row lock:
        1. Acquire SELECT FOR UPDATE on the Event row.
        2. Count ENROLLED rows inside the lock (authoritative seat count).
        3. If capacity is met, raise CapacityFullException (HTTP 400).
        4. If the seeker has a CANCELED record, transition it to ENROLLED.
           Otherwise create a new Enrollment row.

    The partial-unique constraint (status='ENROLLED') on (event, seeker)
    provides a database-level backstop against double-active enrollments.
    """
    permission_classes = [IsSeeker]

    def post(self, request, pk):
        with transaction.atomic():
            # Step 1 — Lock the Event row to serialize concurrent enrollments
            event = (
                Event.objects
                .select_for_update()
                .filter(pk=pk)
                .first()
            )
            if not event:
                raise BaseCustomException(
                    detail="Event not found.",
                    code="event_not_found",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            # Step 2 — Check if seeker already has an active enrollment
            existing = (
                Enrollment.objects
                .filter(event=event, seeker=request.user)
                .order_by('-created_at')
                .first()
            )
            if existing and existing.status == EnrollmentStatus.ENROLLED:
                raise AlreadyEnrolledException()

            # Step 3 — Authoritative seat count inside the lock
            active_count = Enrollment.objects.filter(
                event=event,
                status=EnrollmentStatus.ENROLLED,
            ).count()

            if event.capacity is not None and active_count >= event.capacity:
                raise CapacityFullException()

            # Step 4 — Transition state or create new enrollment
            if existing and existing.status == EnrollmentStatus.CANCELED:
                # Re-enrollment: CANCELED → ENROLLED
                existing.status = EnrollmentStatus.ENROLLED
                existing.save(update_fields=['status', 'updated_at'])
                enrollment = existing
                http_status = status.HTTP_200_OK
                detail_msg = 'Re-enrolled successfully.'
            else:
                enrollment = Enrollment.objects.create(
                    event=event,
                    seeker=request.user,
                    status=EnrollmentStatus.ENROLLED,
                )
                http_status = status.HTTP_201_CREATED
                detail_msg = 'Successfully enrolled in event.'

        serializer = EnrollmentSerializer(enrollment)
        return Response(
            {'detail': detail_msg, 'enrollment': serializer.data},
            status=http_status,
        )


class CancelEnrollmentView(APIView):
    """
    POST /api/v1/events/<pk>/cancel/  — Cancel an active enrollment (Seeker only).

    Transitions status from ENROLLED → CANCELED.
    The vacated seat becomes immediately available for other seekers.
    """
    permission_classes = [IsSeeker]

    def post(self, request, pk):
        with transaction.atomic():
            event = Event.objects.filter(pk=pk).first()
            if not event:
                raise BaseCustomException(
                    detail="Event not found.",
                    code="event_not_found",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            enrollment = Enrollment.objects.filter(
                event=event,
                seeker=request.user,
                status=EnrollmentStatus.ENROLLED,
            ).first()

            if not enrollment:
                raise EnrollmentNotFoundException()

            enrollment.status = EnrollmentStatus.CANCELED
            enrollment.save(update_fields=['status', 'updated_at'])

        serializer = EnrollmentSerializer(enrollment)
        return Response(
            {'detail': 'Enrollment successfully canceled.', 'enrollment': serializer.data},
            status=status.HTTP_200_OK,
        )


class MyEnrollmentsView(generics.ListAPIView):
    """
    GET /api/v1/events/my-enrollments/

    Return the authenticated seeker's full enrollment history (all statuses),
    most recent first.
    """
    serializer_class = EnrollmentSerializer
    permission_classes = [IsSeeker]

    def get_queryset(self):
        return (
            Enrollment.objects
            .filter(seeker=self.request.user)
            .select_related('event', 'event__created_by', 'seeker')
            .order_by('-created_at')
        )
