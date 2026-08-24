from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from users.views import (
    SignupView,
    VerifyOTPView,
    ResendOTPView,
    LoginView,
    MeView,
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('me/', MeView.as_view(), name='me'),
]
