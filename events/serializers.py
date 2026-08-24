from rest_framework import serializers
from events.models import Event, Enrollment, EnrollmentStatus

class EventSerializer(serializers.ModelSerializer):
    enrolled_count = serializers.IntegerField(read_only=True)
    available_seats = serializers.IntegerField(read_only=True)
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

    def validate(self, attrs):
        starts_at = attrs.get('starts_at')
        ends_at = attrs.get('ends_at')
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({'ends_at': 'Event end time must be after start time.'})
        return attrs

class EnrollmentSerializer(serializers.ModelSerializer):
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
