import uuid
from datetime import UTC, datetime

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "accept-encoding",
}


def get_service_urls() -> dict[str, str]:
    return {
        "auth": (getattr(settings, "AUTH_SERVICE_URL", "") or "").rstrip("/"),
        "exam": (getattr(settings, "EXAM_SERVICE_URL", "") or "").rstrip("/"),
        "grading": (getattr(settings, "GRADING_SERVICE_URL", "") or "").rstrip("/"),
        "results": (getattr(settings, "RESULTS_SERVICE_URL", "") or "").rstrip("/"),
    }


def get_or_create_request_id(request) -> str:
    incoming = request.headers.get("X-Request-ID", "").strip()
    # Accept safe UUID/alphanumeric IDs or generate a fresh one
    if (
        incoming
        and len(incoming) <= 64
        and all(c.isalnum() or c in "-_" for c in incoming)
    ):
        return incoming
    return str(uuid.uuid4())


def forward_request(request, service_key: str, identity=None) -> HttpResponse:
    service_urls = get_service_urls()
    base_url = service_urls.get(service_key, "")
    if not base_url:
        return JsonResponse(
            {"error": f"Upstream service '{service_key}' is not configured"},
            status=503,
        )

    max_bytes = getattr(settings, "MAX_BODY_BYTES", 2 * 1024 * 1024)
    if len(request.body) > max_bytes:
        return JsonResponse({"error": "Request payload too large"}, status=413)

    request_id = get_or_create_request_id(request)
    target_url = f"{base_url}{request.path}"
    if request.META.get("QUERY_STRING"):
        target_url = f"{target_url}?{request.META['QUERY_STRING']}"

    outbound_headers = {}
    for key, value in request.headers.items():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            outbound_headers[key] = value

    # Attach trusted gateway metadata (never trust client-supplied identity headers)
    outbound_headers["X-Request-ID"] = request_id
    outbound_headers["X-Forwarded-By"] = "pyproctor-api-gateway"
    outbound_headers["Accept-Encoding"] = "identity"

    internal_secret = getattr(settings, "GATEWAY_INTERNAL_SECRET", "")
    if internal_secret:
        outbound_headers["X-Gateway-Secret"] = internal_secret

    if identity is not None:
        outbound_headers["X-User-Id"] = identity.user_id
        outbound_headers["X-User-Role"] = identity.role
        if identity.email:
            outbound_headers["X-User-Email"] = identity.email

    timeout = getattr(settings, "UPSTREAM_TIMEOUT_SECONDS", 10)

    try:
        upstream_resp = requests.request(
            method=request.method,
            url=target_url,
            headers=outbound_headers,
            data=request.body if request.body else None,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.Timeout:
        return JsonResponse(
            {
                "error": f"Upstream service '{service_key}' timed out",
                "requestId": request_id,
            },
            status=504,
        )
    except requests.RequestException:
        return JsonResponse(
            {
                "error": f"Upstream service '{service_key}' unavailable",
                "requestId": request_id,
            },
            status=502,
        )

    response = HttpResponse(
        content=upstream_resp.content,
        status=upstream_resp.status_code,
        content_type=upstream_resp.headers.get("Content-Type", "application/json"),
    )
    response["X-Request-ID"] = request_id
    return response


def probe_service_health(base_url: str, timeout: float = 3.0) -> str:
    if not base_url:
        return "NOT_CONFIGURED"
    for path in ("/health", "/api/v1/health"):
        try:
            resp = requests.get(f"{base_url}{path}", timeout=timeout)
            if 200 <= resp.status_code < 300:
                return "UP"
        except requests.RequestException:
            continue
    return "DOWN"


def aggregated_health_response() -> JsonResponse:
    urls = get_service_urls()
    services_status = {
        "auth": probe_service_health(urls["auth"]),
        "exam": probe_service_health(urls["exam"]),
        "grading": probe_service_health(urls["grading"]),
        "results": probe_service_health(urls["results"]),
    }

    # Gateway is UP; mark HTTP 200 unless auth is DOWN when configured
    all_up = all(
        status in ("UP", "NOT_CONFIGURED") for status in services_status.values()
    )
    status_code = 200 if all_up else 503

    return JsonResponse(
        {
            "gateway": "UP",
            "services": services_status,
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        status=status_code,
    )
