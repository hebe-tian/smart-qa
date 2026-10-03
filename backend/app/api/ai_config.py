"""AI config blueprint: CRUD + connection test (Feature 3)."""
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.ai_config import AIConfig
from app.core.security import encrypt_api_key, decrypt_api_key
from app.core.decorators import token_required
from app.services.logging_service import get_logger

ai_config_bp = Blueprint("ai_config", __name__)
logger = get_logger("api")


@ai_config_bp.route("", methods=["GET"])
@token_required
def list_configs():
    configs = AIConfig.query.order_by(AIConfig.created_at.desc()).all()
    return jsonify({"configs": [c.to_dict() for c in configs]})


@ai_config_bp.route("/<int:config_id>", methods=["GET"])
@token_required
def get_config(config_id):
    config = AIConfig.query.get_or_404(config_id)
    return jsonify(config.to_dict(include_key=False))


@ai_config_bp.route("", methods=["POST"])
@token_required
def create_config():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    base_url = data.get("base_url", "").strip()
    api_key = data.get("api_key", "").strip()
    model = data.get("model", "").strip()
    config_type = data.get("config_type", "both").strip() or "both"

    if not name or not base_url or not api_key:
        return jsonify({"error": "Name, base_url, and api_key are required"}), 400

    # For non-embedding types, model is required
    if config_type != "embedding" and not model:
        return jsonify({"error": "Model is required for chat/both config types"}), 400

    # For embedding-only configs, model can be empty (use placeholder)
    if not model:
        model = data.get("embedding_model", "").strip() or "n/a"

    config = AIConfig(
        name=name,
        base_url=base_url,
        api_key_encrypted=encrypt_api_key(api_key),
        model=model,
        temperature=float(data.get("temperature", 0.7)),
        max_tokens=int(data.get("max_tokens", 4096)),
        embedding_model=data.get("embedding_model", "").strip() or None,
        config_type=config_type,
        is_default=data.get("is_default", False),
        is_active=data.get("is_active", True),
    )
    db.session.add(config)
    db.session.commit()

    # If set as default, unset others of compatible types
    if config.is_default:
        _set_default(config.id)

    logger.info("AI config created: id=%d name=%s", config.id, config.name)
    return jsonify(config.to_dict()), 201


@ai_config_bp.route("/<int:config_id>", methods=["PUT"])
@token_required
def update_config(config_id):
    config = AIConfig.query.get_or_404(config_id)
    data = request.get_json() or {}

    if "name" in data:
        config.name = data["name"].strip()
    if "base_url" in data:
        config.base_url = data["base_url"].strip()
    if "api_key" in data and data["api_key"]:
        config.api_key_encrypted = encrypt_api_key(data["api_key"].strip())
    if "model" in data:
        config.model = data["model"].strip()
    if "temperature" in data:
        config.temperature = float(data["temperature"])
    if "max_tokens" in data:
        config.max_tokens = int(data["max_tokens"])
    if "embedding_model" in data:
        config.embedding_model = data["embedding_model"].strip() or None
    if "config_type" in data:
        config.config_type = data["config_type"].strip() or "both"
    if "is_active" in data:
        config.is_active = data["is_active"]
    if "is_default" in data and data["is_default"]:
        _set_default(config_id)
    elif "is_default" in data and not data["is_default"]:
        config.is_default = False

    db.session.commit()
    logger.info("AI config updated: id=%d", config_id)
    return jsonify(config.to_dict())


@ai_config_bp.route("/<int:config_id>", methods=["DELETE"])
@token_required
def delete_config(config_id):
    config = AIConfig.query.get_or_404(config_id)
    db.session.delete(config)
    db.session.commit()
    logger.info("AI config deleted: id=%d", config_id)
    return jsonify({"message": "Config deleted"})


@ai_config_bp.route("/<int:config_id>/test", methods=["POST"])
@token_required
def test_connection(config_id):
    """Test AI connection status (Feature 3)."""
    config = AIConfig.query.get_or_404(config_id)

    from app.services.ai_service import AIService
    ai_service = AIService(config, user_id=g.current_user_id)
    success, message = ai_service.test_connection()

    from datetime import datetime
    config.connection_status = "connected" if success else "failed"
    config.last_tested_at = datetime.utcnow()
    db.session.commit()

    # Track config_test event
    from app.services.analytics_service import AnalyticsService
    AnalyticsService().track_event(
        user_id=g.current_user_id,
        event_type="config_test",
        event_data={"config_id": config_id, "success": success, "message": message},
    )

    logger.info("AI connection test: id=%d success=%s msg=%s", config_id, success, message)
    return jsonify({"success": success, "message": message, "connection_status": config.connection_status})


def _set_default(config_id):
    """Set a config as default, unset others of compatible types.

    A "both" config clears all other defaults.
    A "chat" config clears defaults on other "chat" and "both" configs.
    An "embedding" config clears defaults on other "embedding" and "both" configs.
    """
    config = AIConfig.query.get(config_id)
    if not config:
        return

    config.is_default = True

    ct = config.config_type or "both"
    if ct == "both":
        others = AIConfig.query.filter(AIConfig.id != config_id).all()
    elif ct == "chat":
        others = AIConfig.query.filter(
            AIConfig.id != config_id,
            AIConfig.config_type.in_(["chat", "both"]),
        ).all()
    elif ct == "embedding":
        others = AIConfig.query.filter(
            AIConfig.id != config_id,
            AIConfig.config_type.in_(["embedding", "both"]),
        ).all()
    else:
        others = AIConfig.query.filter(AIConfig.id != config_id).all()

    for c in others:
        c.is_default = False
    db.session.commit()
