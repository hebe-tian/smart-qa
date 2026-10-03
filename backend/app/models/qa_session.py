"""QA message model for multi-round requirement clarification."""
from datetime import datetime
from app.extensions import db


class QAMessage(db.Model):
    __tablename__ = "qa_messages"

    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey("requirements.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user / assistant
    content = db.Column(db.Text, nullable=False)
    round = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "requirement_id": self.requirement_id,
            "role": self.role,
            "content": self.content,
            "round": self.round,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
