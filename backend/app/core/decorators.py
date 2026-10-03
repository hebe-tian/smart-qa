"""Flask decorators: token auth, event tracking."""
from functools import wraps
from flask import request, g, jsonify
from app.core.security import verify_token


def token_required(f):
    """Decorator to require JWT token authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header"}), 401

        token = auth_header[7:]
        payload = verify_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        g.current_user_id = payload.get("user_id")
        g.current_username = payload.get("username")
        # Old tokens issued before the guest feature have no role -> treat as "user"
        g.current_role = payload.get("role", "user")
        return f(*args, **kwargs)
    return decorated


def track_event(event_type):
    """Decorator to track an analytics event on endpoint completion."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            result = f(*args, **kwargs)
            try:
                from app.services.analytics_service import AnalyticsService
                svc = AnalyticsService()
                user_id = getattr(g, "current_user_id", None)
                svc.track_event(
                    user_id=user_id,
                    event_type=event_type,
                    event_data={"endpoint": request.path, "method": request.method},
                    page_url=request.path,
                    ip_address=request.remote_addr,
                    ua=request.headers.get("User-Agent", ""),
                )
            except Exception:
                pass  # Analytics should never break the main flow
            return result
        return wrapped
    return decorator
