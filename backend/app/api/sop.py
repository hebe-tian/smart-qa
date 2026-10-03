"""SOP blueprint: generate SOP from Q&A, list/view/edit, index to KB, template management."""
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.core.decorators import token_required
from app.models.sop import SOP
from app.services.logging_service import get_logger

sop_bp = Blueprint("sop", __name__)
logger = get_logger("api")


def _service():
    from app.services.sop_service import SOPService
    return SOPService()


@sop_bp.route("", methods=["GET"])
@token_required
def list_sops():
    """List all SOPs for the current user (newest first)."""
    sops = _service().list_sops(g.current_user_id)
    return jsonify({"sops": sops})


@sop_bp.route("/generate", methods=["POST"])
@token_required
def generate_sop():
    """Generate a SOP from a Q&A session's answer.

    Request body: {"session_id": int, "message_id": int?}
    One SOP per session (idempotent).
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    message_id = data.get("message_id")

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    try:
        sop = _service().generate_from_session(
            int(session_id), g.current_user_id,
            message_id=int(message_id) if message_id else None,
        )
        return jsonify({"sop": sop}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        logger.error("SOP generate failed: session_id=%s error=%s", session_id, str(e))
        return jsonify({"error": f"生成失败：{str(e)}"}), 500


@sop_bp.route("/template", methods=["GET"])
@token_required
def get_template():
    """Get the current SOP format template."""
    return jsonify({"template": _service().get_template()})


@sop_bp.route("/template", methods=["PUT"])
@token_required
def update_template():
    """Update the SOP format template."""
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")

    try:
        result = _service().update_template(content, g.current_user_id)
        return jsonify({"template": result["content"]})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@sop_bp.route("/template/reset", methods=["POST"])
@token_required
def reset_template():
    """Reset the SOP format template to the built-in default."""
    result = _service().reset_template(g.current_user_id)
    return jsonify({"template": result["content"]})


@sop_bp.route("/session/<int:session_id>", methods=["GET"])
@token_required
def get_session_sop(session_id):
    """Get the SOP linked to a Q&A session (if any)."""
    sop = _service().get_session_sop(session_id, g.current_user_id)
    if not sop:
        return jsonify({"sop": None})
    return jsonify({"sop": sop})


@sop_bp.route("/<int:sop_id>", methods=["GET"])
@token_required
def get_sop(sop_id):
    """Get a single SOP (ownership-checked) with indexed flag."""
    sop = _service().get_sop_dict(sop_id, g.current_user_id)
    if not sop:
        return jsonify({"error": "SOP not found"}), 404
    return jsonify(sop)


@sop_bp.route("/<int:sop_id>", methods=["PUT"])
@token_required
def update_sop(sop_id):
    """Edit a SOP's title and content (ownership-checked)."""
    sop = SOP.query.get(sop_id)
    if not sop or sop.user_id != g.current_user_id:
        return jsonify({"error": "SOP not found"}), 404

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"error": "title and content are required"}), 400

    sop.title = title
    sop.content = content
    db.session.commit()
    logger.info("SOP updated: id=%d user_id=%s", sop_id, g.current_user_id)
    return jsonify(_service().get_sop_dict(sop_id, g.current_user_id))


@sop_bp.route("/<int:sop_id>/index", methods=["POST"])
@token_required
def index_sop(sop_id):
    """Index a SOP into the knowledge base (RAG)."""
    try:
        result = _service().index_to_kb(sop_id, g.current_user_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error("SOP index failed: id=%d error=%s", sop_id, str(e))
        return jsonify({"error": f"构建知识库失败：{str(e)}"}), 500


@sop_bp.route("/<int:sop_id>", methods=["DELETE"])
@token_required
def delete_sop(sop_id):
    """Delete a SOP (ownership-checked). Also removes its KB index chunks."""
    sop = SOP.query.get(sop_id)
    if not sop or sop.user_id != g.current_user_id:
        return jsonify({"error": "SOP not found"}), 404

    # Remove indexed chunks for this SOP so stale vectors don't linger
    from app.models.embedding import Embedding
    Embedding.query.filter_by(chunk_type="sop", source_id=sop_id).delete()

    db.session.delete(sop)
    db.session.commit()
    logger.info("SOP deleted: id=%d user_id=%s", sop_id, g.current_user_id)
    return jsonify({"message": "SOP deleted"})
