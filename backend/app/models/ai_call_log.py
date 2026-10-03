"""AI call log model - stores every AI API call record."""
from datetime import datetime
from app.extensions import db


class AICallLog(db.Model):
    __tablename__ = "ai_call_logs"

    id = db.Column(db.Integer, primary_key=True)
    ai_config_id = db.Column(db.Integer, db.ForeignKey("ai_configs.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    requirement_id = db.Column(db.Integer, nullable=True)
    task_type = db.Column(db.String(50), nullable=False)
    # analyze / qa / module_gen / case_gen / regen / test_conn
    model_name = db.Column(db.String(100), nullable=True)
    prompt_messages_json = db.Column(db.Text, nullable=True)
    response_content = db.Column(db.Text, nullable=True)
    prompt_tokens = db.Column(db.Integer, nullable=True)
    completion_tokens = db.Column(db.Integer, nullable=True)
    total_tokens = db.Column(db.Integer, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default="running")  # running/success/failed/timeout
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ai_config = db.relationship("AIConfig")
    user = db.relationship("User")

    def to_dict(self, include_detail=False):
        import json
        d = {
            "id": self.id,
            "ai_config_id": self.ai_config_id,
            "user_id": self.user_id,
            "requirement_id": self.requirement_id,
            "task_type": self.task_type,
            "model_name": self.model_name,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_detail:
            d["prompt_messages"] = json.loads(self.prompt_messages_json) if self.prompt_messages_json else None
            d["response_content"] = self.response_content
        return d
