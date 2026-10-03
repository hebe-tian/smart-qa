"""Knowledge base Q&A session and message models."""
from datetime import datetime
from app.extensions import db


class KBSession(db.Model):
    """A multi-turn Q&A conversation session in the knowledge base."""
    __tablename__ = "kb_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # Auto-derived from the first question, or user-provided
    title = db.Column(db.String(200), nullable=False, default="新问答")
    # active = conversation in progress; answered = AI gave answer; feedback_given = user submitted feedback
    status = db.Column(db.String(20), default="active")  # active/answered/feedback_given
    # positive / negative / null (null = no feedback yet)
    feedback = db.Column(db.String(20), nullable=True)
    feedback_comment = db.Column(db.Text, nullable=True)
    # Whether this session has been indexed into the Embedding table
    indexed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref="kb_sessions")
    messages = db.relationship("KBMessage", backref="session", cascade="all, delete-orphan", order_by="KBMessage.id")

    def to_dict(self, include_messages=False):
        d = {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "status": self.status,
            "feedback": self.feedback,
            "feedback_comment": self.feedback_comment,
            "indexed": self.indexed,
            "message_count": len(self.messages) if self.messages else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_messages:
            d["messages"] = [m.to_dict() for m in self.messages]
        return d


class KBMessage(db.Model):
    """A single message within a KBSession (user question, AI clarification, or AI answer)."""
    __tablename__ = "kb_messages"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("kb_sessions.id"), nullable=False)
    # user / assistant
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    # question (user asking) / clarification (AI follow-up) / answer (AI final answer)
    message_type = db.Column(db.String(20), default="question")
    round = db.Column(db.Integer, default=1)
    # RAG sources JSON (for answer messages), nullable
    sources_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_sources(self):
        import json
        return json.loads(self.sources_json) if self.sources_json else []

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "message_type": self.message_type,
            "round": self.round,
            "sources": self.get_sources(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
