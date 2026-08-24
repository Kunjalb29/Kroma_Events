from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.db import transaction

from common.exceptions import BaseCustomException, UnverifiedUserException
from users.models import UserProfile
from users.serializers import (
    SignupSerializer,
    VerifyOTPSerializer,
    ResendOTPSerializer,
    LoginSerializer,
)
from users.services import (
    generate_unique_username,
    create_and_send_otp,
    verify_user_otp,
)

class SignupView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        role = serializer.validated_data['role']

        with transaction.atomic():
            username = generate_unique_username(email)
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_active=True
            )
            profile = UserProfile.objects.create(
                user=user,
                role=role,
                is_verified=False
            )
            create_and_send_otp(user)

        return Response({
            'detail': 'User registered successfully. An OTP has been sent to your email address.',
            'email': user.email,
            'role': profile.role,
            'is_verified': profile.is_verified
        }, status=status.HTTP_201_CREATED)

class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].strip().lower()
        otp_code = serializer.validated_data['otp'].strip()

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise BaseCustomException(
                detail="User with this email was not found.",
                code="user_not_found",
                status_code=status.HTTP_404_NOT_FOUND
            )

        verify_user_otp(user, otp_code)

        return Response({
            'detail': 'Email verified successfully. You can now log in.',
            'is_verified': True
        }, status=status.HTTP_200_OK)

class ResendOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise BaseCustomException(
                detail="User with this email was not found.",
                code="user_not_found",
                status_code=status.HTTP_404_NOT_FOUND
            )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.is_verified:
            raise BaseCustomException(
                detail="Account is already verified.",
                code="already_verified",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        create_and_send_otp(user)

        return Response({
            'detail': 'A new OTP has been sent to your email address.'
        }, status=status.HTTP_200_OK)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].strip().lower()
        password = serializer.validated_data['password']

        user = User.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(password):
            raise BaseCustomException(
                detail="Invalid email or password.",
                code="invalid_credentials",
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.is_verified:
            raise UnverifiedUserException()

        refresh = RefreshToken.for_user(user)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'role': profile.role,
                'is_verified': profile.is_verified
            }
        }, status=status.HTTP_200_OK)
