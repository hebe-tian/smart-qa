"""Export blueprint: export test cases in multiple formats."""
import io

from flask import Blueprint, request, jsonify, send_file, g
from app.core.decorators import token_required
from app.core.ownership import check_requirement_owner
from app.services.export_service import ExportService
from app.services.logging_service import get_logger

logger = get_logger("api")

export_bp = Blueprint("export", __name__)

_VALID_FORMATS = ("html", "md", "xmind")


@export_bp.route("/<int:req_id>", methods=["GET"])
@token_required
def export_cases(req_id):
    """Export all modules and cases of a requirement in the specified format."""
    fmt = (request.args.get("format") or "").strip().lower()
    if fmt not in _VALID_FORMATS:
        return jsonify({"error": f"不支持的格式，请选择: {', '.join(_VALID_FORMATS)}"}), 400

    check_requirement_owner(req_id)

    svc = ExportService()
    try:
        filename, content, mimetype = svc.generate(req_id, fmt)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Export failed (req_id={req_id}, fmt={fmt}): {e}")
        return jsonify({"error": "导出失败，请稍后重试"}), 500

    logger.info(
        f"User {g.current_username} exported req {req_id} as {fmt} -> {filename}"
    )

    return send_file(
        io.BytesIO(content),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )
