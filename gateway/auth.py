from dataclasses import dataclass

import jwt
from django.conf import settings

SPOOFABLE_HEADERS = {
    "HTTP_X_USER_ID",
    "HTTP_X_USER_EMAIL",
    "HTTP_X_USER_ROLE",
    "HTTP_X_GATEWAY_AUTH",
}

GRADING_ALLOWED_ROLES = {"INSTRUCTOR", "SYSTEM", "INTERNAL_SERVICE", "ADMIN"}


class GatewayAuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class VerifiedIdentity:
    user_id: str
    email: str
    role: str


def extract_bearer_token(request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    return token or None


def verify_jwt(token: str) -> VerifiedIdentity:
    secret = getattr(settings, "JWT_SECRET", "")
    if not secret:
        raise GatewayAuthError(
            "JWT verification is not configured on gateway", status_code=500
        )

    algorithm = getattr(settings, "JWT_ALGORITHM", "HS256")
    issuer = getattr(settings, "JWT_ISSUER", None)

    options = {"require": ["exp", "sub"]}
    decode_kwargs = {
        "key": secret,
        "algorithms": [algorithm],
        "options": options,
    }
    if issuer:
        decode_kwargs["issuer"] = issuer

    try:
        payload = jwt.decode(token, **decode_kwargs)
    except jwt.ExpiredSignatureError as exc:
        raise GatewayAuthError("Token has expired", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise GatewayAuthError("Invalid authentication token", status_code=401) from exc

    user_id = str(
        payload.get("sub") or payload.get("userId") or payload.get("user_id") or ""
    ).strip()
    role = str(payload.get("role") or "").strip().upper()
    email = str(payload.get("email") or "").strip()

    if not user_id:
        raise GatewayAuthError("Token missing subject claim", status_code=401)

    return VerifiedIdentity(user_id=user_id, email=email, role=role)


def authorize_route(request, service_key: str) -> VerifiedIdentity | None:
    """
    - auth: public (rate-limited at gateway; auth_service handles /me & /logout tokens)
    - grading: requires valid JWT + INSTRUCTOR or internal system role
    - exams / results: requires valid JWT
    """
    if service_key == "auth":
        return None

    token = extract_bearer_token(request)
    if not token:
        raise GatewayAuthError("Missing Bearer token", status_code=401)

    identity = verify_jwt(token)

    if service_key == "grading" and identity.role not in GRADING_ALLOWED_ROLES:
        raise GatewayAuthError(
            "Forbidden: requires INSTRUCTOR or internal system role",
            status_code=403,
        )

    return identity
