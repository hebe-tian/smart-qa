"""Tasks blueprint: polling for async AI generation status."""
from flask import Blueprint, jsonify
from app.services.task_store import task_store
from app.core.decorators import token_required

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.route("/<task_id>/status", methods=["GET"])
@token_required
def get_task_status(task_id):
    """Poll task status. Returns {status, progress, message, error}."""
    task = task_store.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    # Cleanup old tasks occasionally
    if task["status"] in ("completed", "failed"):
        task_store.cleanup_old()

    return jsonify({
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "message": task["message"],
        "error": task["error"],
    })


@tasks_bp.route("/<task_id>/result", methods=["GET"])
@token_required
def get_task_result(task_id):
    """Get task result data after completion."""
    task = task_store.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if task["status"] not in ("completed", "failed"):
        return jsonify({"error": "Task not finished", "status": task["status"]}), 400

    return jsonify({
        "task_id": task_id,
        "status": task["status"],
        "result": task["result"],
        "error": task["error"],
    })
