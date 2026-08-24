from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException, ValidationError
from rest_framework import status

class BaseCustomException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'An error occurred.'
    default_code = 'error'

    def __init__(self, detail=None, code=None, status_code=None):
        if status_code is not None:
            self.status_code = status_code
        if detail is not None:
            self.detail = detail
        else:
            self.detail = self.default_detail
        if code is not None:
            self.code = code
        else:
            self.code = self.default_code
        super().__init__(detail=self.detail, code=self.code)

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
    default_detail = 'Seeker is already actively enrolled in this event.'
    default_code = 'already_enrolled'

class EnrollmentNotFoundException(BaseCustomException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = 'Active enrollment for this event was not found.'
    default_code = 'enrollment_not_found'

def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler ensuring standard response shape:
    {"detail": "...", "code": "..."}
    """
    response = exception_handler(exc, context)

    if response is not None:
        detail_msg = ""
        code_str = getattr(exc, 'default_code', 'error')
        if hasattr(exc, 'code') and exc.code:
            code_str = str(exc.code)

        if isinstance(response.data, dict):
            # Check if DRF or serializer validation error dictionary
            if 'detail' in response.data:
                raw_detail = response.data['detail']
                if hasattr(raw_detail, 'code'):
                    code_str = str(raw_detail.code)
                detail_msg = str(raw_detail)
            elif 'non_field_errors' in response.data:
                raw_errors = response.data['non_field_errors']
                if isinstance(raw_errors, list) and len(raw_errors) > 0:
                    detail_msg = str(raw_errors[0])
                else:
                    detail_msg = str(raw_errors)
                code_str = 'invalid_input'
            else:
                # Format serializer errors: field_name: error message
                formatted_errors = []
                for field, errors in response.data.items():
                    if isinstance(errors, list):
                        msg = errors[0]
                    else:
                        msg = str(errors)
                    formatted_errors.append(f"{field}: {msg}")
                detail_msg = "; ".join(formatted_errors)
                code_str = 'invalid_input'

        elif isinstance(response.data, list):
            if len(response.data) > 0:
                detail_msg = str(response.data[0])
            else:
                detail_msg = "An error occurred."
            code_str = 'invalid_input'
        else:
            detail_msg = str(response.data)

        # Standard error response shape
        response.data = {
            'detail': detail_msg,
            'code': code_str
        }

    return response
