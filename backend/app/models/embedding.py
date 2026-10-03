"""Embedding model: stores vector data for RAG knowledge base."""
import json
from datetime import datetime
from app.extensions import db


class Embedding(db.Model):
    __tablename__ = "embeddings"

    id = db.Column(db.Integer, primary_key=True)
    # 'requirement' / 'module' / 'test_case'
    chunk_type = db.Column(db.String(20), nullable=False)
    project_type = db.Column(db.String(20), default="production")  # production/test
    # FK to the source record (requirement.id / module.id / test_case.id)
    source_id = db.Column(db.Integer, nullable=False)
    # Redundant requirement_id for efficient filtering by requirement
    requirement_id = db.Column(db.Integer, nullable=False)
    # module_id for test_case chunks (NULL for requirement/module chunks)
    module_id = db.Column(db.Integer, nullable=True)
    # Original chunk text that was embedded
    text = db.Column(db.Text, nullable=False)
    # Vector stored as raw bytes (numpy.ndarray.tobytes())
    embedding = db.Column(db.LargeBinary, nullable=False)
    # Vector dimension (e.g. 1536 for text-embedding-3-small)
    dim = db.Column(db.Integer, nullable=False)
    # Extra metadata: priority, case_type, module_name, etc.
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_metadata(self):
        """Deserialize metadata JSON to dict."""
        return json.loads(self.metadata_json) if self.metadata_json else {}

    def to_dict(self):
        """Serialize for API responses (excludes raw embedding bytes)."""
        return {
            "id": self.id,
            "chunk_type": self.chunk_type,
            "project_type": self.project_type or "production",
            "source_id": self.source_id,
            "requirement_id": self.requirement_id,
            "module_id": self.module_id,
            "text": self.text,
            "dim": self.dim,
            "metadata": self.get_metadata(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
