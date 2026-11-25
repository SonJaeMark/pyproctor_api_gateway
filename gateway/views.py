# gateway/views.py
# Add to gateway/views.py
import hmac
from datetime import UTC, datetime

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .auth import GatewayAuthError, authorize_route
from .probe import run_health_checks, wake_microservices
from .proxy import aggregated_health_response, forward_request, get_or_create_request_id
from .ratelimit import is_auth_rate_limited


def _authorize_ops_request(request) -> tuple[bool, str]:
    configured_token = getattr(settings, "OPS_WAKE_TOKEN", "")
    if not configured_token:
        return True, ""
    provided_token = request.headers.get("X-Ops-Token", "")
    if hmac.compare_digest(provided_token, configured_token):
        return True, ""
    return False, "Unauthorized: invalid or missing X-Ops-Token"


@require_GET
def check_microservice(request):
    allowed, reason = _authorize_ops_request(request)
    if not allowed:
        return JsonResponse({"error": reason}, status=401)

    timeout = float(getattr(settings, "HEALTH_CHECK_TIMEOUT_SECONDS", 5.0))
    report = run_health_checks(timeout=timeout)
    status_code = 200 if report["allHealthy"] else 503
    return JsonResponse(report, status=status_code)


@require_http_methods(["GET", "POST"])
def wake_services(request):
    allowed, reason = _authorize_ops_request(request)
    if not allowed:
        return JsonResponse({"error": reason}, status=401)

    wake_timeout = float(getattr(settings, "WAKE_TIMEOUT_SECONDS", 35.0))
    report = wake_microservices(timeout=wake_timeout)
    status_code = 200 if report["allHealthy"] else 202
    return JsonResponse(report, status=status_code)


@require_GET
def liveness_health(request):
    return JsonResponse(
        {
            "gateway": "UP",
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        status=200,
    )


@require_GET
def system_health(request):
    return aggregated_health_response()


@csrf_exempt
def route_to_service(request, service_key: str, subpath: str = ""):
    request_id = get_or_create_request_id(request)

    if service_key == "auth":
        limited, retry_after = is_auth_rate_limited(request)
        if limited:
            resp = JsonResponse(
                {
                    "error": "Too many authentication requests. Please try again later.",
                    "retryAfter": retry_after,
                    "requestId": request_id,
                },
                status=429,
            )
            resp["Retry-After"] = str(retry_after)
            resp["X-Request-ID"] = request_id
            return resp

    try:
        identity = authorize_route(request, service_key)
    except GatewayAuthError as exc:
        resp = JsonResponse(
            {"error": exc.message, "requestId": request_id},
            status=exc.status_code,
        )
        resp["X-Request-ID"] = request_id
        return resp

    return forward_request(request, service_key=service_key, identity=identity)
