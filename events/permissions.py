from rest_framework import permissions
from users.models import UserRole


class IsFacilitator(permissions.BasePermission):
    """
    Grants access only to authenticated users with the FACILITATOR role
    who also have a verified profile.
    """
    message = "Only verified facilitators can perform this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        try:
            return request.user.profile.role == UserRole.FACILITATOR
        except Exception:
            return False


class IsSeeker(permissions.BasePermission):
    """
    Grants access only to authenticated users with the SEEKER role.
    """
    message = "Only seekers can perform this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        try:
            return request.user.profile.role == UserRole.SEEKER
        except Exception:
            return False


class IsEventOwner(permissions.BasePermission):
    """
    Object-level permission: allows mutation only if the request user created the event.
    """
    message = "You do not have permission to modify this event."

    def has_object_permission(self, request, view, obj):
        return obj.created_by == request.user


class IsEventOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission:
    - Safe methods (GET, HEAD, OPTIONS) are allowed for any authenticated user.
    - Write methods require the request user to be the event owner.
    """
    message = "Only the event creator can modify or delete this event."

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.created_by == request.user
