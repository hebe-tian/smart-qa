"""AI configuration model."""
from datetime import datetime
from app.extensions import db


class AIConfig(db.Model):
    __tablename__ = "ai_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    base_url = db.Column(db.String(500), nullable=False)
    api_key_encrypted = db.Column(db.Text, nullable=False)
    model = db.Column(db.String(100), nullable=False)
    temperature = db.Column(db.Float, default=0.7)
    max_tokens = db.Column(db.Integer, default=4096)
    # Embedding model name (e.g. text-embedding-3-small); empty = RAG disabled
    embedding_model = db.Column(db.String(100), nullable=True)
    # Config type: "chat" (对话), "embedding" (向量), "both" (两者)
    config_type = db.Column(db.String(20), default="both")
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    connection_status = db.Column(db.String(20), default="unknown")  # unknown/connected/failed
    last_tested_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_key=False):
        from app.core.security import decrypt_api_key
        d = {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "api_key": decrypt_api_key(self.api_key_encrypted) if include_key else "***",
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "embedding_model": self.embedding_model or "",
            "config_type": self.config_type or "both",
            "is_default": self.is_default,
            "is_active": self.is_active,
            "connection_status": self.connection_status,
            "last_tested_at": self.last_tested_at.isoformat() if self.last_tested_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        return d

    # ------------------------------------------------------------------
    # Type-aware default config queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_default_chat_config():
        """Get the default AI config for chat/analysis/generation operations.

        Looks for configs with config_type 'chat' or 'both' that are
        marked as default and active.
        """
        return AIConfig.query.filter(
            AIConfig.is_default == True,  # noqa: E712
            AIConfig.is_active == True,  # noqa: E712
            AIConfig.config_type.in_(["chat", "both"]),
        ).first()

    @staticmethod
    def get_default_embedding_config():
        """Get the default AI config for embedding/RAG operations.

        Looks for configs with config_type 'embedding' or 'both' that are
        marked as default and active, and have embedding_model set.
        """
        return AIConfig.query.filter(
            AIConfig.is_default == True,  # noqa: E712
            AIConfig.is_active == True,  # noqa: E712
            AIConfig.config_type.in_(["embedding", "both"]),
        ).first()
