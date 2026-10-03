"""Code blueprint: upload/list/delete/index business code documents."""
from flask import Blueprint, request, jsonify, g
from app.core.decorators import token_required
from app.services.logging_service import get_logger

code_bp = Blueprint("code", __name__)
logger = get_logger("api")


@code_bp.route("/upload-zip", methods=["POST"])
@token_required
def upload_zip():
    """Upload a zip archive of code files and import them.

    Multipart form data:
        - file: .zip archive (required)
        - title: document title (required)
        - description: optional description
    """
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file uploaded"}), 400
    if not file.filename.lower().endswith(".zip"):
        return jsonify({"error": "Only .zip files are supported"}), 400

    title = (request.form.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    description = request.form.get("description", "").strip()

    from app.services.code_service import CodeService
    service = CodeService(user_id=g.current_user_id)
    try:
        result = service.import_zip(file, g.current_user_id, title, description)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Zip import failed: %s", str(e))
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


@code_bp.route("/documents", methods=["GET"])
@token_required
def list_documents():
    """List all code documents for the current user."""
    from app.services.code_service import CodeService
    service = CodeService(user_id=g.current_user_id)
    docs = service.list_documents(g.current_user_id)
    return jsonify({"documents": docs})


@code_bp.route("/documents/<int:doc_id>", methods=["DELETE"])
@token_required
def delete_document(doc_id):
    """Delete a code document and its embeddings."""
    from app.services.code_service import CodeService
    service = CodeService(user_id=g.current_user_id)
    if not service.delete_document(doc_id, g.current_user_id):
        return jsonify({"error": "Document not found"}), 404
    return jsonify({"message": "Document deleted"})


@code_bp.route("/documents/<int:doc_id>/index", methods=["POST"])
@token_required
def index_document(doc_id):
    """Index a single code document (chunk + embed + store)."""
    from app.services.code_service import CodeService
    service = CodeService(user_id=g.current_user_id)
    try:
        stored = service.index_document(doc_id)
        return jsonify({"status": "success", "chunk_count": stored})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error("Code index failed: doc_id=%d error=%s", doc_id, str(e))
        return jsonify({"error": f"Index failed: {str(e)}"}), 500


@code_bp.route("/rebuild", methods=["POST"])
@token_required
def rebuild_all():
    """Re-index all code documents for the current user."""
    from app.services.code_service import CodeService
    service = CodeService(user_id=g.current_user_id)
    try:
        result = service.rebuild_all(user_id=g.current_user_id)
        return jsonify(result)
    except Exception as e:
        logger.error("Code rebuild failed: %s", str(e))
        return jsonify({"error": f"Rebuild failed: {str(e)}"}), 500
