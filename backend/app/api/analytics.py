"""Analytics blueprint: track events + summary + events feed."""
from flask import Blueprint, request, jsonify, g
from app.services.analytics_service import AnalyticsService
from app.core.decorators import token_required

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/track", methods=["POST"])
@token_required
def track_event():
    """Frontend analytics tracking endpoint."""
    data = request.get_json() or {}
    event_type = data.get("event_type", "")
    event_data = data.get("event_data")
    page_url = data.get("page_url", request.headers.get("Referer", ""))

    if not event_type:
        return jsonify({"error": "event_type is required"}), 400

    AnalyticsService().track_event(
        user_id=g.current_user_id,
        event_type=event_type,
        event_data=event_data,
        page_url=page_url,
        ip_address=request.remote_addr,
        ua=request.headers.get("User-Agent", ""),
    )

    return jsonify({"status": "tracked"}), 201


@analytics_bp.route("/summary", methods=["GET"])
@token_required
def get_summary():
    """Get aggregated analytics summary."""
    svc = AnalyticsService()
    summary = svc.get_summary()
    token_trend = svc.get_token_trend(days=7)
    return jsonify({"summary": summary, "token_trend": token_trend})


@analytics_bp.route("/events", methods=["GET"])
@token_required
def get_events():
    """Get paginated analytics events."""
    event_type = request.args.get("event_type")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    result = AnalyticsService().get_events(event_type=event_type, page=page, per_page=per_page)
    return jsonify(result)
