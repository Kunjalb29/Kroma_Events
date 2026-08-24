from rest_framework import serializers
from django.contrib.auth.models import User
from users.models import UserProfile, UserRole


class SignupSerializer(serializers.Serializer):
    """
    Validates signup input.
    - Rejects any `username` field in the request payload.
    - Enforces unique email (case-insensitive).
    - Accepts only valid UserRole choices.
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    role = serializers.ChoiceField(choices=UserRole.choices, required=True)

    def validate(self, attrs):
        # Strict rejection of `username` in the incoming payload
        initial_data = getattr(self, 'initial_data', {})
        if 'username' in initial_data:
            raise serializers.ValidationError(
                'The `username` field is not accepted. Usernames are auto-generated from your email.'
            )

        email = attrs.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                {'email': 'A user with this email address already exists.'}
            )

        attrs['email'] = email
        return attrs


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, max_length=6, min_length=6)

    def validate_otp(self, value):
        if not value.strip().isdigit():
            raise serializers.ValidationError("OTP must be a 6-digit numeric code.")
        return value.strip()


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)


class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'email', 'username', 'role', 'is_verified', 'created_at']
        read_only_fields = ['id', 'email', 'username', 'is_verified', 'created_at']
