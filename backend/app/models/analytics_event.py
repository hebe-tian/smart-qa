"""Analytics event model for user behavior tracking."""
from datetime import datetime
from app.extensions import db


class AnalyticsEvent(db.Model):
    __tablename__ = "analytics_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    # page_view / click / generate_start / generate_complete / regenerate / qa_round / config_test / login / logout
    event_data_json = db.Column(db.Text, nullable=True)
    page_url = db.Column(db.String(500), nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref="events")

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "event_data": json.loads(self.event_data_json) if self.event_data_json else None,
            "page_url": self.page_url,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
