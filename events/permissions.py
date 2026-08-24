from rest_framework import permissions
from users.models import UserRole

class IsFacilitator(permissions.BasePermission):
    """
    Permission check for Facilitator role.
    """
    message = "Only facilitators can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == UserRole.FACILITATOR
        )

class IsSeeker(permissions.BasePermission):
    """
    Permission check for Seeker role.
    """
    message = "Only seekers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == UserRole.SEEKER
        )

class IsEventOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to allow only owners of an event to edit or delete it.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.created_by == request.user
