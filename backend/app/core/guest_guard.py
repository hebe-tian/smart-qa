"""Guest guard: app-level read-only enforcement for guest sessions.

Guests (JWT role == "guest") may browse business data via GET requests but:
- All write methods (POST/PUT/DELETE/PATCH) are rejected with 403, except a
  small whitelist (guest login, normal login/register, analytics tracking).
- Sensitive endpoints (AI config, call logs, code upload, KB QA) are
  fully blocked, preventing guests from reading API keys or internal logs.
- SOP is readable by guests (global read-only); its writes are still blocked
  by the read-only rule below.

Requests without a valid guest token are not touched here; per-endpoint
``token_required`` keeps handling authentication as before.
"""
from flask import request, jsonify
from app.core.security import verify_token

# Write requests guests are still allowed to perform.
_WRITE_WHITELIST = {
    ("POST", "/api/auth/guest"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/analytics/track"),
}

# Sensitive API prefixes fully blocked for guests (any method).
# Note: /api/kbqa (QA sessions) and /api/sop (SOP docs) stay readable — those
# are business pages guests may browse read-only; writes are blocked by the
# read-only rule below.
_SENSITIVE_PREFIXES = (
    "/api/ai-config",
    "/api/call-logs",
    "/api/code",
)

# Sensitive prefixes with per-path exceptions.
_PREFIX_EXCEPTIONS = {
    "/api/rag": {("GET", "/api/rag/status")},
}

_READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}

GUEST_MESSAGE = "游客仅可浏览，不能操作"


def _get_role_from_request():
    """Extract role from the Authorization header. Returns None if not a guest."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    payload = verify_token(auth_header[7:])
    if not payload:
        return None
    return payload.get("role", "user")


def register_guest_guard(app):
    """Register the before_request guest guard on the Flask app."""
    @app.before_request
    def guest_guard():
        # Only enforce on API routes; static pages are hidden by the frontend.
        if not request.path.startswith("/api/"):
            return None

        if _get_role_from_request() != "guest":
            return None

        # 1. Fully blocked sensitive endpoints
        for prefix in _SENSITIVE_PREFIXES:
            if request.path.startswith(prefix):
                return jsonify({"error": "游客无权访问该资源"}), 403

        # 2. Sensitive endpoints with exceptions (e.g. read-only status)
        for prefix, exceptions in _PREFIX_EXCEPTIONS.items():
            if request.path.startswith(prefix):
                if (request.method, request.path) not in exceptions:
                    return jsonify({"error": "游客无权访问该资源"}), 403

        # 3. Read-only enforcement: block write methods except whitelist
        if request.method not in _READ_ONLY_METHODS:
            if (request.method, request.path) not in _WRITE_WHITELIST:
                return jsonify({"error": GUEST_MESSAGE}), 403

        return None
