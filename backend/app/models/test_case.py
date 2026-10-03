"""Test case model."""
from datetime import datetime
import json
from app.extensions import db


class TestCase(db.Model):
    __tablename__ = "test_cases"

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    preconditions = db.Column(db.Text, nullable=True)
    steps_json = db.Column(db.Text, nullable=True)  # JSON list of step strings
    expected_result = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(20), default="medium")  # high/medium/low
    case_type = db.Column(db.String(50), default="functional")  # functional/boundary/exception/performance
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "module_id": self.module_id,
            "title": self.title,
            "preconditions": self.preconditions or "",
            "steps": json.loads(self.steps_json) if self.steps_json else [],
            "expected_result": self.expected_result or "",
            "priority": self.priority,
            "case_type": self.case_type,
            "order": self.order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
