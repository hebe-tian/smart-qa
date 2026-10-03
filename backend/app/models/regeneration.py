"""Regeneration log model."""
from datetime import datetime
from app.extensions import db


class RegenerationLog(db.Model):
    __tablename__ = "regeneration_logs"

    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column(db.String(20), nullable=False)  # case / module
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    old_snapshot = db.Column(db.Text, nullable=True)  # JSON snapshot of original
    new_snapshot = db.Column(db.Text, nullable=True)  # JSON snapshot of regenerated
    status = db.Column(db.String(20), default="pending")  # pending/running/completed/failed
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="regeneration_logs")

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason": self.reason,
            "description": self.description,
            "old_snapshot": json.loads(self.old_snapshot) if self.old_snapshot else None,
            "new_snapshot": json.loads(self.new_snapshot) if self.new_snapshot else None,
            "status": self.status,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
