"""Logging middleware: request/response logging for API endpoints only."""
import time
from flask import request, g


# File extensions for frontend static resources — skip logging
_STATIC_EXTENSIONS = (
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map", ".webp",
)

_STATIC_PREFIXES = ("/css/", "/js/", "/assets/", "/fonts/")


def _is_static_request(path):
    """Check if the request is for a frontend static resource."""
    if any(path.startswith(p) for p in _STATIC_PREFIXES):
        return True
    if any(path.endswith(ext) for ext in _STATIC_EXTENSIONS):
        return True
    return False


class LoggingMiddleware:
    """Middleware for HTTP request/response logging.

    - Frontend resource requests (CSS/JS/images/HTML): NOT logged
    - Successful backend API requests (/api/*): DEBUG only
    - Errors (5xx) and warnings (4xx): always logged
    """

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        from app.services.logging_service import get_logger
        self.logger = get_logger("middleware")

        @app.before_request
        def before_request():
            # Start time is still required by after_request to compute duration.
            # No REQUEST log here: the RESPONSE line already carries method,
            # path, status and duration, so an entry line only doubles the noise.
            g.request_start_time = time.time()

        @app.after_request
        def after_request(response):
            duration_ms = 0
            if hasattr(g, "request_start_time"):
                duration_ms = int((time.time() - g.request_start_time) * 1000)

            # Skip logging for frontend resource requests entirely
            if _is_static_request(request.path):
                # Still set response time header and track page views
                response.headers["X-Response-Time-ms"] = str(duration_ms)

                # Auto track page views for HTML pages
                if response.status_code == 200 and request.path.endswith(".html"):
                    try:
                        from app.services.analytics_service import AnalyticsService
                        svc = AnalyticsService()
                        svc.track_event(
                            user_id=getattr(g, "current_user_id", None),
                            event_type="page_view",
                            event_data={"page": request.path},
                            page_url=request.path,
                            ip_address=request.remote_addr,
                            ua=request.headers.get("User-Agent", ""),
                        )
                    except Exception:
                        pass
                return response

            # Log backend requests with appropriate level.
            # Healthy responses are debug-only; only 4xx/5xx stay in the logs.
            status = response.status_code
            if status >= 500:
                self.logger.error(
                    "RESPONSE %s %s -> %d (%dms)",
                    request.method, request.path, status, duration_ms,
                )
            elif status >= 400:
                self.logger.warning(
                    "RESPONSE %s %s -> %d (%dms)",
                    request.method, request.path, status, duration_ms,
                )
            else:
                self.logger.debug(
                    "RESPONSE %s %s -> %d (%dms)",
                    request.method, request.path, status, duration_ms,
                )

            # Auto track page views for HTML pages (non-static path serving HTML)
            if response.status_code == 200 and request.path.endswith(".html"):
                try:
                    from app.services.analytics_service import AnalyticsService
                    svc = AnalyticsService()
                    svc.track_event(
                        user_id=getattr(g, "current_user_id", None),
                        event_type="page_view",
                        event_data={"page": request.path},
                        page_url=request.path,
                        ip_address=request.remote_addr,
                        ua=request.headers.get("User-Agent", ""),
                    )
                except Exception:
                    pass

            response.headers["X-Response-Time-ms"] = str(duration_ms)
            return response
