# gateway/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path("api/v1/health", views.system_health, name="gateway-system-health"),
    path("api/v1/wake", views.wake_services, name="gateway-api-wake"),
    path(
        "api/v1/auth/<path:subpath>",
        views.route_to_service,
        {"service_key": "auth"},
        name="gateway-auth-subpath",
    ),
    path(
        "api/v1/auth",
        views.route_to_service,
        {"service_key": "auth", "subpath": ""},
        name="gateway-auth-root",
    ),
    path(
        "api/v1/exams/<path:subpath>",
        views.route_to_service,
        {"service_key": "exam"},
        name="gateway-exams-subpath",
    ),
    path(
        "api/v1/exams",
        views.route_to_service,
        {"service_key": "exam", "subpath": ""},
        name="gateway-exams-root",
    ),
    path(
        "api/v1/grading/<path:subpath>",
        views.route_to_service,
        {"service_key": "grading"},
        name="gateway-grading-subpath",
    ),
    path(
        "api/v1/grading",
        views.route_to_service,
        {"service_key": "grading", "subpath": ""},
        name="gateway-grading-root",
    ),
    path(
        "api/v1/results/<path:subpath>",
        views.route_to_service,
        {"service_key": "results"},
        name="gateway-results-subpath",
    ),
    path(
        "api/v1/results",
        views.route_to_service,
        {"service_key": "results", "subpath": ""},
        name="gateway-results-root",
    ),
]
