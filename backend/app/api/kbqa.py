"""KB QA blueprint: multi-turn Q&A sessions with feedback."""
from flask import Blueprint, request, jsonify, g
from app.core.decorators import token_required
from app.services.logging_service import get_logger

kbqa_bp = Blueprint("kbqa", __name__)
logger = get_logger("api")


def _get_configs():
    """Get default embedding and chat configs for KB QA."""
    from app.models.ai_config import AIConfig
    emb_config = AIConfig.get_default_embedding_config()
    if not emb_config or not emb_config.embedding_model:
        return None, None, "No default embedding configuration found. Please configure an embedding model first."
    chat_config = AIConfig.get_default_chat_config()
    if not chat_config:
        return None, None, "No default chat model configuration found. Please configure a chat model first."
    return emb_config, chat_config, None


@kbqa_bp.route("/sessions", methods=["POST"])
@token_required
def create_session():
    """Create a new Q&A session.

    Request body (optional): {"title": "..."}
    """
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip() or None

    from app.services.kb_qa_service import KBQAService
    emb_config, chat_config, err = _get_configs()
    if err:
        return jsonify({"error": err}), 400

    service = KBQAService(emb_config, chat_config=chat_config, user_id=g.current_user_id)
    session = service.create_session(g.current_user_id, title=title)
    return jsonify(session.to_dict()), 201


@kbqa_bp.route("/sessions", methods=["GET"])
@token_required
def list_sessions():
    """List all Q&A sessions for the current user."""
    from app.services.kb_qa_service import KBQAService
    service = KBQAService(None, user_id=g.current_user_id)
    sessions = service.list_sessions(g.current_user_id)
    return jsonify({"sessions": sessions})


@kbqa_bp.route("/sessions/<int:session_id>", methods=["GET"])
@token_required
def get_session(session_id):
    """Get a session with all messages."""
    from app.services.kb_qa_service import KBQAService
    service = KBQAService(None, user_id=g.current_user_id)
    session = service.get_session(session_id, user_id=g.current_user_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session)


@kbqa_bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@token_required
def delete_session(session_id):
    """Delete a session and all its messages."""
    from app.services.kb_qa_service import KBQAService
    service = KBQAService(None, user_id=g.current_user_id)
    if not service.delete_session(session_id, g.current_user_id):
        return jsonify({"error": "Session not found"}), 404
    return jsonify({"message": "Session deleted"})


@kbqa_bp.route("/sessions/<int:session_id>/messages", methods=["POST"])
@token_required
def send_message(session_id):
    """Send a message in a Q&A session.

    Request body: {"content": "...", "force_answer": false}
    - content: The user's question or clarification response.
    - force_answer: If true, AI will skip clarification and answer directly.

    Response: {"message_type": "clarification"|"answer", "content": "...", "sources": [...], "round": N, "session_status": "..."}
    """
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    force_answer = bool(data.get("force_answer", False))

    if not content:
        return jsonify({"error": "Content is required"}), 400

    from app.services.kb_qa_service import KBQAService
    emb_config, chat_config, err = _get_configs()
    if err:
        return jsonify({"error": err}), 400

    service = KBQAService(emb_config, chat_config=chat_config, user_id=g.current_user_id)
    try:
        result = service.send_message(session_id, content, force_answer=force_answer)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error("KB QA send_message failed: session_id=%d error=%s", session_id, str(e))
        return jsonify({"error": f"Message failed: {str(e)}"}), 500


@kbqa_bp.route("/sessions/<int:session_id>/feedback", methods=["POST"])
@token_required
def submit_feedback(session_id):
    """Submit feedback for a Q&A session.

    Request body: {"feedback": "positive"|"negative", "comment": "..."}
    - positive: Session will be indexed as chunk_type="qa" (verified correct)
    - negative: Session will be indexed as chunk_type="qa_negative" (incorrect reference)

    Response: {"indexed": true/false, "chunk_type": "qa"|"qa_negative"}
    """
    data = request.get_json(silent=True) or {}
    feedback = (data.get("feedback") or "").strip().lower()
    comment = (data.get("comment") or "").strip() or None

    if feedback not in ("positive", "negative"):
        return jsonify({"error": "Feedback must be 'positive' or 'negative'"}), 400

    from app.services.kb_qa_service import KBQAService
    emb_config, chat_config, err = _get_configs()
    if err:
        return jsonify({"error": err}), 400

    service = KBQAService(emb_config, chat_config=chat_config, user_id=g.current_user_id)
    try:
        result = service.submit_feedback(session_id, feedback, comment)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error("KB QA feedback failed: session_id=%d error=%s", session_id, str(e))
        return jsonify({"error": f"Feedback failed: {str(e)}"}), 500
