from django.urls import path
from events.views import (
    EventListCreateView,
    EventDetailView,
    EnrollEventView,
    CancelEnrollmentView,
    MyEnrollmentsView,
)

urlpatterns = [
    path('', EventListCreateView.as_view(), name='event-list-create'),
    path('my-enrollments/', MyEnrollmentsView.as_view(), name='my-enrollments'),
    path('<int:pk>/', EventDetailView.as_view(), name='event-detail'),
    path('<int:pk>/enroll/', EnrollEventView.as_view(), name='event-enroll'),
    path('<int:pk>/cancel/', CancelEnrollmentView.as_view(), name='event-cancel'),
]
