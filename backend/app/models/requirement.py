"""Requirement model."""
from datetime import datetime
from app.extensions import db


class Requirement(db.Model):
    __tablename__ = "requirements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="draft")  # draft/analyzing/qa/generating/completed
    project_type = db.Column(db.String(20), default="production")  # production/test
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref="requirements")
    qa_messages = db.relationship("QAMessage", backref="requirement", cascade="all, delete-orphan")
    modules = db.relationship("Module", backref="requirement", cascade="all, delete-orphan")

    def to_dict(self, include_modules=False):
        d = {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "status": self.status,
            "project_type": self.project_type or "production",
            "user_id": self.user_id,
            "module_count": len(self.modules) if self.modules else 0,
            "case_count": sum(len(m.cases) for m in self.modules) if self.modules else 0,
            "qa_rounds": max((q.round for q in self.qa_messages), default=0) if self.qa_messages else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_modules:
            d["modules"] = [m.to_dict() for m in self.modules]
        return d
