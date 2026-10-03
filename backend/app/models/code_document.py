"""Code document model: stores user-uploaded or GitHub-pulled business code."""
from datetime import datetime
from app.extensions import db


class CodeDocument(db.Model):
    """A business code file uploaded locally or pulled from GitHub, indexed for RAG."""
    __tablename__ = "code_documents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    # github / local
    source_type = db.Column(db.String(20), default="local")
    # Original URL for github source, nullable for local uploads
    source_url = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(200), nullable=False)
    # Relative path within an uploaded folder (preserves directory structure)
    relative_path = db.Column(db.String(500), nullable=True)
    # python / javascript / java / text / etc.
    language = db.Column(db.String(20), default="text")
    content = db.Column(db.Text, nullable=False)
    chunk_count = db.Column(db.Integer, default=0)
    indexed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="code_documents")

    def to_dict(self):
        # Exclude raw content from list responses to keep payload small
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "file_name": self.file_name,
            "relative_path": self.relative_path,
            "language": self.language,
            "content_length": len(self.content) if self.content else 0,
            "chunk_count": self.chunk_count,
            "indexed": self.indexed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
