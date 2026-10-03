"""RAG blueprint: knowledge base query, rebuild, and status."""
from flask import Blueprint, request, jsonify, g
from app.core.decorators import token_required
from app.services.logging_service import get_logger

rag_bp = Blueprint("rag", __name__)
logger = get_logger("api")


@rag_bp.route("/status", methods=["GET"])
@token_required
def get_status():
    """Get knowledge base index status: chunk_count, last_built_at, is_ready."""
    from app.services.embedding_service import EmbeddingService
    status = EmbeddingService.get_status()
    status["embedding_configured"] = EmbeddingService.is_configured()
    return jsonify(status)


@rag_bp.route("/query", methods=["POST"])
@token_required
def query():
    """Execute a RAG query.

    Request body: {"question": "...", "top_k": 5}
    Response: {"answer": "...", "sources": [...], "search_time_ms": N}
    """
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    top_k = int(data.get("top_k", 5))

    if not question:
        return jsonify({"error": "Question is required"}), 400

    if top_k < 1 or top_k > 20:
        top_k = 5

    # Get embedding config for RAG
    from app.models.ai_config import AIConfig
    config = AIConfig.get_default_embedding_config()
    if not config:
        return jsonify({"error": "No active default embedding configuration found. Please configure an embedding model first."}), 400

    if not config.embedding_model:
        return jsonify({
            "error": "Embedding model is not configured. Please set an embedding model in AI Config."
        }), 400

    # Get chat config for answer generation
    chat_config = AIConfig.get_default_chat_config()
    if not chat_config:
        return jsonify({"error": "No active chat model configuration found. Please configure a chat model first."}), 400

    # Check if knowledge base has data
    from app.services.embedding_service import EmbeddingService
    status = EmbeddingService.get_status()
    if not status["is_ready"]:
        return jsonify({
            "error": "Knowledge base is empty. Please rebuild the index first."
        }), 400

    try:
        from app.services.rag_service import RAGService
        rag = RAGService(config, chat_config=chat_config, user_id=g.current_user_id)
        result = rag.query(question, top_k=top_k)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("RAG query failed: %s", str(e))
        return jsonify({"error": "RAG query failed. Please try again."}), 500


@rag_bp.route("/rebuild", methods=["POST"])
@token_required
def rebuild():
    """Rebuild the knowledge base index.

    Request body (optional): {"project_type": "production"|"test"|null}
    - If omitted, defaults to "production" (test-type data is excluded from the KB).
    - If "production" or "test", only rebuild that project type.
    - If null, rebuild all (both production and test).

    Response: {"status": "success", "chunk_count": N, "project_type": ...}
    """
    data = request.get_json(silent=True) or {}
    project_type = data.get("project_type", "production")

    from app.models.ai_config import AIConfig
    config = AIConfig.get_default_embedding_config()
    if not config:
        return jsonify({"error": "No active default embedding configuration found."}), 400

    if not config.embedding_model:
        return jsonify({
            "error": "Embedding model is not configured. Please set an embedding model in AI Config."
        }), 400

    try:
        from app.services.rag_service import RAGService
        rag = RAGService(config, user_id=g.current_user_id)
        result = rag.rebuild(project_type=project_type)
        return jsonify(result)
    except Exception as e:
        logger.error("RAG rebuild failed: %s", str(e))
        return jsonify({"error": "Rebuild failed. Please try again."}), 500
