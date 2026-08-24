from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q, Count, F, ExpressionWrapper, IntegerField
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

class EventListCreateView(generics.ListCreateAPIView):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Event.objects.annotate(
            enrolled_count_annotated=Count(
                'enrollments',
                filter=Q(enrollments__status=EnrollmentStatus.ENROLLED)
            )
        ).select_related('created_by').order_by('starts_at')

        req = self.request
        q = req.query_params.get('q')
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            )

        location = req.query_params.get('location')
        if location:
            queryset = queryset.filter(location__icontains=location)

        language = req.query_params.get('language')
        if language:
            queryset = queryset.filter(language__icontains=language)

        starts_after = req.query_params.get('starts_after')
        if starts_after:
            dt = parse_datetime(starts_after)
            if dt:
                queryset = queryset.filter(starts_at__gte=dt)

        starts_before = req.query_params.get('starts_before')
        if starts_before:
            dt = parse_datetime(starts_before)
            if dt:
                queryset = queryset.filter(starts_at__lte=dt)

        return queryset

    def perform_create(self, serializer):
        if not (self.request.user and hasattr(self.request.user, 'profile') and self.request.user.profile.role == 'FACILITATOR'):
            raise BaseCustomException(
                detail="Only users with the FACILITATOR role can create events.",
                code="permission_denied",
                status_code=status.HTTP_403_FORBIDDEN
            )
        serializer.save(created_by=self.request.user)

class EventDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsEventOwnerOrReadOnly]

    def get_queryset(self):
        return Event.objects.annotate(
            enrolled_count_annotated=Count(
                'enrollments',
                filter=Q(enrollments__status=EnrollmentStatus.ENROLLED)
            )
        ).select_related('created_by')

    def perform_update(self, serializer):
        if not (self.request.user and hasattr(self.request.user, 'profile') and self.request.user.profile.role == 'FACILITATOR'):
            raise BaseCustomException(
                detail="Only facilitators can modify events.",
                code="permission_denied",
                status_code=status.HTTP_403_FORBIDDEN
            )
        serializer.save()

    def perform_destroy(self, instance):
        if not (self.request.user and hasattr(self.request.user, 'profile') and self.request.user.profile.role == 'FACILITATOR'):
            raise BaseCustomException(
                detail="Only facilitators can delete events.",
                code="permission_denied",
                status_code=status.HTTP_403_FORBIDDEN
            )
        instance.delete()

class EnrollEventView(APIView):
    permission_classes = [IsSeeker]

    def post(self, request, pk):
        try:
            with transaction.atomic():
                # Lock Event row explicitly to prevent race conditions under concurrent enrollments
                event = Event.objects.select_for_update().filter(pk=pk).first()
                if not event:
                    raise BaseCustomException(
                        detail="Event not found.",
                        code="event_not_found",
                        status_code=status.HTTP_404_NOT_FOUND
                    )

                # Check existing enrollment status for seeker
                existing_enrollment = Enrollment.objects.filter(
                    event=event,
                    seeker=request.user
                ).first()

                if existing_enrollment and existing_enrollment.status == EnrollmentStatus.ENROLLED:
                    raise AlreadyEnrolledException()

                # Explicit seat count calculation inside the lock
                active_enrolled_count = Enrollment.objects.filter(
                    event=event,
                    status=EnrollmentStatus.ENROLLED
                ).count()

                if event.capacity is not None and active_enrolled_count >= event.capacity:
                    raise CapacityFullException()

                if existing_enrollment: # Re-enrollment state transition: CANCELED -> ENROLLED
                    existing_enrollment.status = EnrollmentStatus.ENROLLED
                    existing_enrollment.save(update_fields=['status', 'updated_at'])
                    enrollment = existing_enrollment
                else:
                    enrollment = Enrollment.objects.create(
                        event=event,
                        seeker=request.user,
                        status=EnrollmentStatus.ENROLLED
                    )

            serializer = EnrollmentSerializer(enrollment)
            return Response({
                'detail': 'Successfully enrolled in event.',
                'enrollment': serializer.data
            }, status=status.HTTP_201_CREATED)

        except (BaseCustomException, Exception) as exc:
            if isinstance(exc, BaseCustomException):
                raise exc
            raise exc

class CancelEnrollmentView(APIView):
    permission_classes = [IsSeeker]

    def post(self, request, pk):
        with transaction.atomic():
            event = Event.objects.filter(pk=pk).first()
            if not event:
                raise BaseCustomException(
                    detail="Event not found.",
                    code="event_not_found",
                    status_code=status.HTTP_404_NOT_FOUND
                )

            enrollment = Enrollment.objects.filter(
                event=event,
                seeker=request.user,
                status=EnrollmentStatus.ENROLLED
            ).first()

            if not enrollment:
                raise EnrollmentNotFoundException()

            enrollment.status = EnrollmentStatus.CANCELED
            enrollment.save(update_fields=['status', 'updated_at'])

        serializer = EnrollmentSerializer(enrollment)
        return Response({
            'detail': 'Enrollment successfully canceled.',
            'enrollment': serializer.data
        }, status=status.HTTP_200_OK)

class MyEnrollmentsView(generics.ListAPIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [IsSeeker]

    def get_queryset(self):
        return Enrollment.objects.filter(seeker=self.request.user).select_related('event', 'seeker').order_by('-created_at')
