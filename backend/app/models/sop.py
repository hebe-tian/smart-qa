"""SOP (standard operating procedure) models."""
from datetime import datetime
from app.extensions import db


class SOP(db.Model):
    """A generated standard operating procedure derived from a Q&A answer."""
    __tablename__ = "sops"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)  # Markdown
    kb_session_id = db.Column(db.Integer, nullable=True, index=True)
    # Idempotency key: one SOP per answer message
    kb_message_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref="sops")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "content": self.content,
            "kb_session_id": self.kb_session_id,
            "kb_message_id": self.kb_message_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SopTemplate(db.Model):
    """Single-row global SOP format template (id=1)."""
    __tablename__ = "sop_template"

    id = db.Column(db.Integer, primary_key=True)  # single row, id=1
    content = db.Column(db.Text, nullable=False)
    updated_by = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "content": self.content,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
