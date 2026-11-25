import hashlib

from django.conf import settings
from django.core.cache import cache


def get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # Take the leftmost client IP; strip whitespace
        first_ip = xff.split(",")[0].strip()
        if first_ip:
            return first_ip
    return request.META.get("REMOTE_ADDR", "unknown")


def is_auth_rate_limited(request) -> tuple[bool, int]:
    """
    Returns (is_limited, retry_after_seconds) for /api/v1/auth/* endpoints.
    """
    limit = getattr(settings, "AUTH_RATE_LIMIT_REQUESTS", 15)
    window = getattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)

    ip = get_client_ip(request)
    ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:24]
    cache_key = f"gw:rl:auth:{ip_hash}"

    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, 1, timeout=window)
        return False, 0

    if current >= limit:
        ttl = cache.ttl(cache_key) if hasattr(cache, "ttl") else window
        return True, max(int(ttl or window), 1)

    try:
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, current + 1, timeout=window)

    return False, 0
