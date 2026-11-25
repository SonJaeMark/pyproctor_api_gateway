import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import requests
from django.conf import settings


def get_configured_services() -> dict[str, str]:
    return {
        "auth": (getattr(settings, "AUTH_SERVICE_URL", "") or "").rstrip("/"),
        "exam": (getattr(settings, "EXAM_SERVICE_URL", "") or "").rstrip("/"),
        "grading": (getattr(settings, "GRADING_SERVICE_URL", "") or "").rstrip("/"),
        "results": (getattr(settings, "RESULTS_SERVICE_URL", "") or "").rstrip("/"),
    }


def _probe_single_health(service_name: str, base_url: str, timeout: float) -> dict:
    if not base_url:
        return {
            "service": service_name,
            "status": "NOT_CONFIGURED",
            "httpStatus": None,
            "latencyMs": None,
            "url": None,
        }

    health_url = f"{base_url}/health"
    start = time.perf_counter()

    try:
        resp = requests.get(
            health_url,
            timeout=timeout,
            headers={"X-Forwarded-By": "pyproctor-api-gateway"},
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        is_up = 200 <= resp.status_code < 300
        return {
            "service": service_name,
            "status": "UP" if is_up else "UNHEALTHY",
            "httpStatus": resp.status_code,
            "latencyMs": latency_ms,
            "url": health_url,
        }
    except requests.Timeout:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {
            "service": service_name,
            "status": "WAKING_OR_TIMEOUT",
            "httpStatus": None,
            "latencyMs": latency_ms,
            "url": health_url,
        }
    except requests.RequestException:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {
            "service": service_name,
            "status": "DOWN",
            "httpStatus": None,
            "latencyMs": latency_ms,
            "url": health_url,
        }


def run_health_checks(timeout: float = 5.0) -> dict:
    services = get_configured_services()
    results: dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=max(len(services), 1)) as pool:
        futures = {
            pool.submit(_probe_single_health, name, url, timeout): name
            for name, url in services.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()

    ordered_results = {name: results[name] for name in services}
    all_healthy = all(
        item["status"] in ("UP", "NOT_CONFIGURED") for item in ordered_results.values()
    )

    return {
        "gateway": "UP",
        "allHealthy": all_healthy,
        "services": ordered_results,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def wake_microservices(timeout: float = 35.0) -> dict:
    """
    Sends concurrent /health requests to wake sleeping Render microservices.
    """
    report = run_health_checks(timeout=timeout)
    report["action"] = "wake"
    return report
