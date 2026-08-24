from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException
from rest_framework import status


# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------

class BaseCustomException(APIException):
    """
    Base class for all Kroma Events domain exceptions.
    Produces the standard error envelope: {"detail": "...", "code": "..."}.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'An error occurred.'
    default_code = 'error'

    def __init__(self, detail=None, code=None, status_code=None):
        if status_code is not None:
            self.status_code = status_code
        detail_val = detail if detail is not None else self.default_detail
        code_val = code if code is not None else self.default_code
        super().__init__(detail=detail_val, code=code_val)


class InvalidOTPException(BaseCustomException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Invalid OTP code provided.'
    default_code = 'otp_invalid'


class OTPExpiredException(BaseCustomException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'OTP has expired. Please request a new one.'
    default_code = 'otp_expired'


class OTPMaxAttemptsException(BaseCustomException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Maximum OTP attempts exceeded. Please request a new OTP.'
    default_code = 'otp_max_attempts_exceeded'


class UnverifiedUserException(BaseCustomException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Account is not verified. Please verify your email via OTP first.'
    default_code = 'user_unverified'


class CapacityFullException(BaseCustomException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Event capacity has been reached.'
    default_code = 'capacity_full'


class AlreadyEnrolledException(BaseCustomException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'You are already actively enrolled in this event.'
    default_code = 'already_enrolled'


class EnrollmentNotFoundException(BaseCustomException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = 'No active enrollment found for this event.'
    default_code = 'enrollment_not_found'


# ---------------------------------------------------------------------------
# Custom exception handler
# ---------------------------------------------------------------------------

def custom_exception_handler(exc, context):
    """
    Global DRF exception handler.

    Normalises every error response to the standard envelope:
        {"detail": "<human-readable message>", "code": "<machine-readable code>"}

    Handles:
    - Custom domain exceptions (BaseCustomException subclasses)
    - DRF built-in exceptions (AuthenticationFailed, PermissionDenied, etc.)
    - DRF serializer ValidationErrors (field-level and non-field-level)
    """
    response = exception_handler(exc, context)

    if response is None:
        return None

    # --- Extract code ---
    code_str = getattr(exc, 'default_code', 'error')

    # For our custom exceptions the code is embedded in exc.detail as an ErrorDetail
    if hasattr(exc, 'detail'):
        detail_obj = exc.detail
        if hasattr(detail_obj, 'code') and detail_obj.code:
            code_str = str(detail_obj.code)
    elif hasattr(exc, 'code') and exc.code:
        code_str = str(exc.code)

    # --- Extract human-readable detail message ---
    data = response.data
    if isinstance(data, dict):
        if 'detail' in data:
            raw = data['detail']
            detail_msg = str(raw)
            # Override code from the ErrorDetail object if richer
            if hasattr(raw, 'code') and raw.code and raw.code != 'error':
                code_str = str(raw.code)
        elif 'non_field_errors' in data:
            errors = data['non_field_errors']
            detail_msg = str(errors[0]) if errors else 'Invalid input.'
            code_str = 'invalid_input'
        else:
            # Field-level validation errors — flatten into a readable string
            parts = []
            for field, errors in data.items():
                if isinstance(errors, list):
                    msg = str(errors[0])
                else:
                    msg = str(errors)
                parts.append(f"{field}: {msg}")
            detail_msg = '; '.join(parts) if parts else 'Invalid input.'
            code_str = 'invalid_input'
    elif isinstance(data, list):
        detail_msg = str(data[0]) if data else 'An error occurred.'
        code_str = 'invalid_input'
    else:
        detail_msg = str(data)

    response.data = {'detail': detail_msg, 'code': code_str}
    return response
