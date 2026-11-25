# PyProctor API Gateway

A Django-based API gateway for routing client requests to the authentication,
exam, grading, and results microservices. The gateway verifies JWTs, applies
route-specific authorization, rate limits authentication traffic, and forwards
trusted request metadata to upstream services.

## Base URL

All versioned endpoints are relative to the gateway base URL:

```text
https://<gateway-host>
```

For local development, the gateway is available at `http://localhost:8000`.

## Endpoints

### Liveness

| Method | Endpoint | Authentication | Description |
| --- | --- | --- | --- |
| `GET` | `/health` | None | Returns gateway liveness only; does not check upstream services. |
| `GET` | `/api/v1/health` | None | Checks every configured upstream service. |
| `GET` | `/check_microservice` | Ops token, if configured | Detailed concurrent health report for every configured service. |
| `GET`, `POST` | `/wake` | Ops token, if configured | Wakes upstream services by probing their `/health` endpoints. |
| `GET`, `POST` | `/api/v1/wake` | Ops token, if configured | API-prefixed wake endpoint. |

Example liveness response:

```json
{
  "gateway": "UP",
  "timestamp": "2026-11-25T00:07:49Z"
}
```

Example system-health response:

```json
{
  "gateway": "UP",
  "services": {
    "auth": "UP",
    "exam": "UP",
    "grading": "UP",
    "results": "UP"
  },
  "timestamp": "2026-11-25T00:07:49Z"
}
```

Service values are `UP`, `DOWN`, or `NOT_CONFIGURED`. `/api/v1/health` returns
`503` when a configured service is unavailable.

`/check_microservice` and the wake endpoints return detailed status objects,
including service name, HTTP status, latency, and probed URL. `/check_microservice`
returns `503` when any configured service is unhealthy. Wake requests return
`202` until all configured services are healthy and `200` once they are.

### Authentication service

| Method | Endpoint | Authentication | Description |
| --- | --- | --- | --- |
| Any | `/api/v1/auth` | None | Proxies to the authentication service root. |
| Any | `/api/v1/auth/<subpath>` | None at the gateway | Proxies the path and query string to the upstream authentication service. |

The authentication endpoints are public at the gateway. Authentication
operations that require a token must be implemented and enforced by the
authentication service, for example protected `/me` or `/logout` routes.

### Exam service

| Method | Endpoint | Authentication | Description |
| --- | --- | --- | --- |
| Any | `/api/v1/exams` | Bearer JWT | Proxies to the exam service root. |
| Any | `/api/v1/exams/<subpath>` | Bearer JWT | Proxies the path and query string to the exam service. |

### Grading service

| Method | Endpoint | Authentication | Description |
| --- | --- | --- | --- |
| Any | `/api/v1/grading` | Bearer JWT with an allowed role | Proxies to the grading service root. |
| Any | `/api/v1/grading/<subpath>` | Bearer JWT with an allowed role | Proxies the path and query string to the grading service. |

Allowed grading roles are `INSTRUCTOR`, `SYSTEM`, `INTERNAL_SERVICE`, and
`ADMIN`.

### Results service

| Method | Endpoint | Authentication | Description |
| --- | --- | --- | --- |
| Any | `/api/v1/results` | Bearer JWT | Proxies to the results service root. |
| Any | `/api/v1/results/<subpath>` | Bearer JWT | Proxies the path and query string to the results service. |

## Request authentication

Protected routes use an HTTP Bearer token:

```http
Authorization: Bearer <jwt>
```

The gateway validates:

- the configured signing secret;
- the configured HMAC algorithm, defaulting to `HS256`;
- the required `exp` and `sub` claims;
- an optional configured issuer;
- the grading route role, where applicable.

The subject can come from `sub`, `userId`, or `user_id`. The gateway maps the
JWT subject, role, and email to trusted downstream headers.

Common authentication responses:

| Status | Meaning |
| --- | --- |
| `401` | Missing, expired, or invalid token; missing subject claim. |
| `403` | Valid token without a grading-authorized role. |
| `500` | JWT verification is not configured. |

## Security features

### JWT verification

JWT validation is performed by PyJWT before protected requests reach an
upstream service. The gateway must share `JWT_SECRET` with the issuing
authentication service. Set `JWT_ISSUER` to the issuer expected in the token.

### Trusted identity propagation

For a successfully authorized protected request, the gateway adds:

```text
X-User-Id: <subject>
X-User-Role: <role>
X-User-Email: <email, if present>
X-Gateway-Secret: <GATEWAY_INTERNAL_SECRET, if configured>
X-Forwarded-By: pyproctor-api-gateway
X-Request-ID: <request id>
```

On protected routes, `X-User-*` values are set only from the verified JWT,
overwriting matching client-supplied values. The auth route is public and does
not add a verified identity; downstream auth services must ignore untrusted
identity headers and enforce their own authorization.

Downstream services should validate `X-Gateway-Secret` or otherwise restrict
network access so that clients cannot bypass the gateway and supply spoofed
identity headers directly.

### Authentication rate limiting

Requests under `/api/v1/auth` are limited by client IP. The default limit is
15 requests per 60-second window.

The response for a limited request is:

```json
{
  "error": "Too many authentication requests. Please try again later.",
  "retryAfter": 60,
  "requestId": "..."
}
```

It includes HTTP `429` and a `Retry-After` header.

Rate limiting uses Django's configured cache. The default local cache is
process-local (`LocMemCache`), so deployments with multiple workers or instances
should use a shared cache backend for consistent limits.

### Operations protection

`/check_microservice`, `/wake`, and `/api/v1/wake` require
`X-Ops-Token` when `OPS_WAKE_TOKEN` is configured:

```http
X-Ops-Token: <operations-token>
```

The token comparison uses constant-time HMAC comparison. A missing or incorrect
token returns `401`.

If `OPS_WAKE_TOKEN` is empty, operations endpoints are intentionally open.
Configure the token in production.

### Request limits and upstream safety

- Request bodies are limited to 2 MiB by default.
- Oversized bodies return `413` with `Request payload too large`.
- Upstream HTTP calls have a 10-second timeout by default.
- Upstream timeouts return `504`; connection/request failures return `502`.
- Redirect following is disabled for upstream requests.
- Hop-by-hop and host headers are not forwarded.
- Incoming `X-Request-ID` values are accepted only when safe and at most 64
  characters; otherwise the gateway generates a UUID.

Every forwarded or gateway-generated error includes `X-Request-ID`, and
gateway-originated JSON responses include `requestId` where applicable.

### Transport and application hardening

Production settings (`DEBUG=0`) enable SSL redirect, secure cookies, HSTS,
content type sniffing protection, and clickjacking protection. Production
deployments should keep Django debug disabled and restrict `ALLOWED_HOSTS`.

The route proxy is CSRF-exempt because it is designed as a stateless API
gateway. Bearer JWT authentication or the public-auth-route policy provides
route protection instead of Django session CSRF checks.

## Configuration

Copy [.env.example](.env.example) and set the following values:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DEBUG` | No | `0` | Enables Django debug behavior when set to `1`. |
| `SECRET_KEY` | Production | Development fallback | Django application secret. |
| `ALLOWED_HOSTS` | No | `localhost,127.0.0.1,.onrender.com` | Comma-separated allowed hosts. |
| `JWT_SECRET` | Protected routes | Empty | Shared JWT signing secret. |
| `JWT_ALGORITHM` | No | `HS256` | PyJWT signing algorithm. |
| `JWT_ISSUER` | No | `pyproctor-auth-service` | Optional required JWT issuer. |
| `AUTH_SERVICE_URL` | Recommended | Default auth service URL | Authentication upstream base URL. |
| `EXAM_SERVICE_URL` | For exams | Empty | Exam upstream base URL. |
| `GRADING_SERVICE_URL` | For grading | `https://grade-service-xh1l.onrender.com` | Grading upstream base URL. |
| `RESULTS_SERVICE_URL` | For results | Empty | Results upstream base URL. |
| `GATEWAY_INTERNAL_SECRET` | Recommended | Empty | Shared secret sent to upstream services. |
| `AUTH_RATE_LIMIT_REQUESTS` | No | `15` | Authentication requests allowed per window. |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Authentication rate-limit window. |
| `UPSTREAM_TIMEOUT_SECONDS` | No | `10` | Upstream proxy request timeout. |
| `MAX_BODY_BYTES` | No | `2097152` | Maximum gateway request body size. |
| `OPS_WAKE_TOKEN` | Production operations | Empty | Required operation bearer token for wake/check routes. |
| `HEALTH_CHECK_TIMEOUT_SECONDS` | No | `5` | Detailed health probe timeout. |
| `WAKE_TIMEOUT_SECONDS` | No | `35` | Wake probe timeout. |

An upstream base URL must not end with `/api/v1/...`; the gateway appends the
full incoming gateway path. For example,
`EXAM_SERVICE_URL=https://exam.example.com` forwards
`/api/v1/exams/attempts` to
`https://exam.example.com/api/v1/exams/attempts`.

## Local development

Install dependencies and run migrations:

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

With Docker Compose:

```bash
docker compose -f compose.dev.yml up --build
```

The development container exposes the gateway on port `8000`.

## Docker production

```bash
docker compose -f compose.prod.yml up --build -d
```

The production image runs Gunicorn with two workers and four threads. Set
`RUN_MIGRATIONS=1` and `COLLECT_STATIC=1` only as needed by the deployment
entrypoint.
