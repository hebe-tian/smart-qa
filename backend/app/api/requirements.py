"""Requirements blueprint: CRUD operations."""
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.requirement import Requirement
from app.models.module import Module
from app.core.decorators import token_required
from app.core.ownership import check_requirement_owner
from app.services.logging_service import get_logger

requirements_bp = Blueprint("requirements", __name__)
logger = get_logger("api")


@requirements_bp.route("", methods=["GET"])
@token_required
def list_requirements():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status = request.args.get("status")
    project_type = request.args.get("project_type")
    search = request.args.get("search", "").strip()

    query = Requirement.query
    if g.current_user_id is not None:
        query = query.filter_by(user_id=g.current_user_id)
    if status:
        query = query.filter_by(status=status)
    if project_type:
        query = query.filter_by(project_type=project_type)
    if search:
        query = query.filter(Requirement.title.contains(search))

    query = query.order_by(Requirement.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "requirements": [r.to_dict() for r in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
    })


@requirements_bp.route("/<int:req_id>", methods=["GET"])
@token_required
def get_requirement(req_id):
    req = check_requirement_owner(req_id)
    return jsonify(req.to_dict(include_modules=True))


@requirements_bp.route("", methods=["POST"])
@token_required
def create_requirement():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()

    if not title or not content:
        return jsonify({"error": "Title and content are required"}), 400

    project_type = data.get("project_type", "production").strip()

    req = Requirement(
        title=title,
        content=content,
        status="draft",
        project_type=project_type,
        user_id=g.current_user_id,
    )
    db.session.add(req)
    db.session.commit()

    logger.info("Requirement created: id=%d title=%s", req.id, req.title)
    return jsonify(req.to_dict()), 201


@requirements_bp.route("/<int:req_id>", methods=["PUT"])
@token_required
def update_requirement(req_id):
    req = check_requirement_owner(req_id)
    data = request.get_json() or {}

    if "title" in data:
        req.title = data["title"].strip()
    if "content" in data:
        req.content = data["content"].strip()
    if "status" in data:
        req.status = data["status"]
    if "project_type" in data:
        req.project_type = data["project_type"]

    db.session.commit()
    logger.info("Requirement updated: id=%d", req_id)
    return jsonify(req.to_dict())


@requirements_bp.route("/<int:req_id>", methods=["DELETE"])
@token_required
def delete_requirement(req_id):
    req = check_requirement_owner(req_id)
    db.session.delete(req)
    db.session.commit()
    logger.info("Requirement deleted: id=%d", req_id)
    return jsonify({"message": "Requirement deleted"})


@requirements_bp.route("/upload", methods=["POST"])
@token_required
def upload_document():
    """Upload a document (PDF/Word/Markdown), parse and AI-extract a structured requirement.

    Multipart form data:
        - file: The document file (.pdf / .docx / .md / .txt)

    Returns {title, content, source_filename} for the frontend to fill into the
    create-requirement form. The requirement is NOT created here — the user reviews
    and edits, then saves via POST /api/requirements.
    """
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file uploaded"}), 400

    from app.services.document_service import DocumentService
    service = DocumentService()
    try:
        result = service.parse_and_extract(file, g.current_user_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Document upload/parse failed: %s", str(e))
        return jsonify({"error": "Document parsing failed. Please check the file format and try again."}), 500
