"""
tests/conftest.py
──────────────────
Shared pytest fixtures for the Kroma Events test suite.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from users.models import UserProfile, UserRole


@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def make_user(db):
    """
    Factory fixture to create a User with associated UserProfile.

    Usage:
        user = make_user(email='x@test.com', role='SEEKER', verified=True)
    """
    def _factory(email, role=UserRole.SEEKER, password='Password123!', verified=True):
        username = email.split('@')[0] + '_test'
        user = User.objects.create_user(
            username=username, email=email, password=password, is_active=True
        )
        UserProfile.objects.create(user=user, role=role, is_verified=verified)
        return user
    return _factory


@pytest.fixture
def verified_seeker(make_user):
    return make_user('default_seeker@example.com', role=UserRole.SEEKER, verified=True)


@pytest.fixture
def verified_facilitator(make_user):
    return make_user('default_facilitator@example.com', role=UserRole.FACILITATOR, verified=True)


@pytest.fixture
def auth_seeker_client(verified_seeker):
    """Authenticated API client for a verified Seeker."""
    client = APIClient()
    client.force_authenticate(user=verified_seeker)
    return client, verified_seeker


@pytest.fixture
def auth_facilitator_client(verified_facilitator):
    """Authenticated API client for a verified Facilitator."""
    client = APIClient()
    client.force_authenticate(user=verified_facilitator)
    return client, verified_facilitator
