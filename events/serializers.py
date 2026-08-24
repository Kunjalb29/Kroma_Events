from rest_framework import serializers
from events.models import Event, Enrollment, EnrollmentStatus


class EventSerializer(serializers.ModelSerializer):
    """
    Full serializer for Event objects.

    `enrolled_count` and `available_seats` are served from model properties
    when accessing a single instance (e.g. detail view) or from queryset
    annotations when available (e.g. list view) — Django REST Framework
    resolves both transparently via `get_attribute`.
    """
    enrolled_count = serializers.SerializerMethodField()
    available_seats = serializers.SerializerMethodField()
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = Event
        fields = [
            'id',
            'title',
            'description',
            'language',
            'location',
            'starts_at',
            'ends_at',
            'capacity',
            'created_by',
            'created_by_email',
            'enrolled_count',
            'available_seats',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_by_email', 'created_at', 'updated_at']

    def get_enrolled_count(self, obj) -> int:
        """Return annotated count when available (list view), else query the property."""
        if hasattr(obj, 'enrolled_count_annotated'):
            return obj.enrolled_count_annotated
        return obj.enrolled_count

    def get_available_seats(self, obj):
        """Return computed available seats, honouring unlimited-capacity events."""
        if obj.capacity is None:
            return None
        enrolled = self.get_enrolled_count(obj)
        return max(0, obj.capacity - enrolled)

    def validate(self, attrs):
        starts_at = attrs.get('starts_at')
        ends_at = attrs.get('ends_at')
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {'ends_at': 'Event end time must be strictly after the start time.'}
            )
        return attrs


class EnrollmentSerializer(serializers.ModelSerializer):
    """
    Serializer for Enrollment objects including denormalized event/seeker info.
    """
    event_title = serializers.CharField(source='event.title', read_only=True)
    event_starts_at = serializers.DateTimeField(source='event.starts_at', read_only=True)
    seeker_email = serializers.EmailField(source='seeker.email', read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            'id',
            'event',
            'event_title',
            'event_starts_at',
            'seeker',
            'seeker_email',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'seeker', 'created_at', 'updated_at']
