"""Module model."""
from datetime import datetime
import json
from app.extensions import db


class Module(db.Model):
    __tablename__ = "modules"

    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey("requirements.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    key_points = db.Column(db.Text, nullable=True)  # JSON list
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cases = db.relationship("TestCase", backref="module", cascade="all, delete-orphan")

    def to_dict(self, include_cases=False):
        d = {
            "id": self.id,
            "requirement_id": self.requirement_id,
            "name": self.name,
            "description": self.description or "",
            "key_points": json.loads(self.key_points) if self.key_points else [],
            "order": self.order,
            "case_count": len(self.cases) if self.cases else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_cases:
            d["cases"] = [c.to_dict() for c in sorted(self.cases or [], key=lambda c: c.order)]
        return d
