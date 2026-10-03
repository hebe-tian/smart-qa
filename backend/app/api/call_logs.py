"""Call logs blueprint: list and detail of AI call records."""
from flask import Blueprint, request, jsonify
from app.models.ai_call_log import AICallLog
from app.core.decorators import token_required

call_logs_bp = Blueprint("call_logs", __name__)


@call_logs_bp.route("", methods=["GET"])
@token_required
def list_call_logs():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    task_type = request.args.get("task_type")
    status = request.args.get("status")

    query = AICallLog.query
    if task_type:
        query = query.filter_by(task_type=task_type)
    if status:
        query = query.filter_by(status=status)

    query = query.order_by(AICallLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "call_logs": [log.to_dict() for log in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
    })


@call_logs_bp.route("/<int:log_id>", methods=["GET"])
@token_required
def get_call_log(log_id):
    log = AICallLog.query.get_or_404(log_id)
    return jsonify(log.to_dict(include_detail=True))


@call_logs_bp.route("/summary", methods=["GET"])
@token_required
def call_log_summary():
    """Return summary stats for call logs."""
    from app.extensions import db
    from sqlalchemy import func

    total = AICallLog.query.count()
    success = AICallLog.query.filter_by(status="success").count()
    failed = AICallLog.query.filter_by(status="failed").count()
    total_tokens = db.session.query(func.coalesce(func.sum(AICallLog.total_tokens), 0)).scalar()

    by_type = db.session.query(
        AICallLog.task_type,
        func.count(AICallLog.id),
    ).group_by(AICallLog.task_type).all()

    return jsonify({
        "total_calls": total,
        "success": success,
        "failed": failed,
        "total_tokens": total_tokens,
        "by_type": {t: c for t, c in by_type},
    })
