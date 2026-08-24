from rest_framework import serializers
from django.contrib.auth.models import User
from users.models import UserProfile, UserRole

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    role = serializers.ChoiceField(choices=UserRole.choices, required=True)

    def validate(self, attrs):
        initial_data = getattr(self, 'initial_data', {})
        if 'username' in initial_data:
            raise serializers.ValidationError(
                {'username': 'The username field is not allowed. Usernames are generated automatically.'}
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

class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['id', 'email', 'role', 'is_verified', 'created_at']
