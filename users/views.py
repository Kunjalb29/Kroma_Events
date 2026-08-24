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
    UserProfileSerializer,
)
from users.services import (
    generate_unique_username,
    create_and_send_otp,
    verify_user_otp,
)


class SignupView(APIView):
    """
    POST /api/v1/auth/signup/

    Register a new user. Accepts `email`, `password`, and `role`.
    Explicitly rejects any `username` field in the payload.
    A unique username is auto-generated internally.
    Sends a 6-digit OTP to the supplied email address on success.
    """
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
                is_active=True,
            )
            profile = UserProfile.objects.create(
                user=user,
                role=role,
                is_verified=False,
            )
            create_and_send_otp(user)

        return Response(
            {
                'detail': (
                    'Account created successfully. '
                    'A 6-digit verification code has been sent to your email address.'
                ),
                'email': user.email,
                'role': profile.role,
                'is_verified': profile.is_verified,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyOTPView(APIView):
    """
    POST /api/v1/auth/verify-otp/

    Verify a user's email address using the 6-digit OTP code sent during signup.
    Enforces a 5-minute TTL and a maximum of 3 failed attempts.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].strip().lower()
        otp_code = serializer.validated_data['otp']

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise BaseCustomException(
                detail="No account found with this email address.",
                code="user_not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        verify_user_otp(user, otp_code)

        return Response(
            {
                'detail': 'Email verified successfully. You may now log in.',
                'is_verified': True,
            },
            status=status.HTTP_200_OK,
        )


class ResendOTPView(APIView):
    """
    POST /api/v1/auth/resend-otp/

    Resend a fresh OTP to the given email address.
    Supersedes (invalidates) any prior active OTP for this user.
    Returns an error if the account is already verified.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise BaseCustomException(
                detail="No account found with this email address.",
                code="user_not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            profile, _ = UserProfile.objects.get_or_create(user=user)

        if profile.is_verified:
            raise BaseCustomException(
                detail="This account is already verified.",
                code="already_verified",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        create_and_send_otp(user)

        return Response(
            {'detail': 'A new verification code has been sent to your email address.'},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    """
    POST /api/v1/auth/login/

    Authenticate a verified user and return a JWT access/refresh token pair.
    Returns HTTP 403 if the account has not completed email verification.
    """
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
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            profile, _ = UserProfile.objects.get_or_create(user=user)

        if not profile.is_verified:
            raise UnverifiedUserException()

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'role': profile.role,
                    'is_verified': profile.is_verified,
                },
            },
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    """
    GET /api/v1/auth/me/

    Return the authenticated user's profile information.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            raise BaseCustomException(
                detail="User profile not found.",
                code="profile_not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)
