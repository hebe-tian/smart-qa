"""Analytics service: user behavior tracking and statistics."""
import json
from datetime import datetime, timedelta
from sqlalchemy import func
from app.extensions import db
from app.models.analytics_event import AnalyticsEvent
from app.models.test_case import TestCase
from app.models.ai_call_log import AICallLog
from app.services.logging_service import get_logger

logger = get_logger("analytics")


class AnalyticsService:
    """Service for tracking user events and generating analytics."""

    def track_event(self, user_id, event_type, event_data=None, page_url=None, ip_address=None, ua=None):
        """Record a single analytics event."""
        try:
            event = AnalyticsEvent(
                user_id=user_id,
                event_type=event_type,
                event_data_json=json.dumps(event_data, ensure_ascii=False) if event_data else None,
                page_url=page_url,
                ip_address=ip_address,
                user_agent=ua,
            )
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            logger.error("Failed to track event %s: %s", event_type, e)
            db.session.rollback()

    def get_summary(self):
        """Return aggregated statistics."""
        total_cases = TestCase.query.count()
        total_calls = AICallLog.query.filter_by(status="success").count()
        total_tokens = db.session.query(
            func.coalesce(func.sum(AICallLog.total_tokens), 0)
        ).filter_by(status="success").scalar()
        total_generates = AnalyticsEvent.query.filter_by(event_type="generate_complete").count()
        success_calls = AICallLog.query.filter_by(status="success").count()
        failed_calls = AICallLog.query.filter_by(status="failed").count()
        total_ai_calls = success_calls + failed_calls
        success_rate = round(success_calls / total_ai_calls * 100, 1) if total_ai_calls > 0 else 0

        return {
            "total_cases": total_cases,
            "total_generates": total_generates,
            "total_ai_calls": total_ai_calls,
            "total_tokens": total_tokens or 0,
            "success_rate": success_rate,
            "success_calls": success_calls,
            "failed_calls": failed_calls,
        }

    def get_events(self, event_type=None, page=1, per_page=20):
        """Get paginated analytics events."""
        query = AnalyticsEvent.query
        if event_type:
            query = query.filter_by(event_type=event_type)
        query = query.order_by(AnalyticsEvent.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            "events": [e.to_dict() for e in pagination.items],
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page,
        }

    def get_token_trend(self, days=7):
        """Get daily token consumption for the last N days."""
        start = datetime.utcnow() - timedelta(days=days)
        logs = AICallLog.query.filter(
            AICallLog.status == "success",
            AICallLog.created_at >= start,
        ).all()

        trend = {}
        for log in logs:
            date_str = log.created_at.strftime("%Y-%m-%d")
            if date_str not in trend:
                trend[date_str] = 0
            trend[date_str] += log.total_tokens or 0

        return [{"date": k, "tokens": v} for k, v in sorted(trend.items())]


analytics_service = AnalyticsService()
