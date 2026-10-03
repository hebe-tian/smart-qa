"""Regenerate blueprint: batch regeneration of cases or modules (Feature 2)."""
import threading
from flask import Blueprint, request, jsonify, g, current_app
from app.models.test_case import TestCase
from app.models.module import Module
from app.services.task_store import task_store
from app.services.case_service import case_service
from app.core.decorators import token_required
from app.services.logging_service import get_logger

regenerate_bp = Blueprint("regenerate", __name__)
logger = get_logger("api")


def _run_with_app_context(app, func, *args):
    """Run a function in a background thread with Flask application context."""
    def _wrapper():
        with app.app_context():
            func(*args)
    return _wrapper


@regenerate_bp.route("", methods=["POST"])
@token_required
def regenerate():
    """Batch regenerate cases or modules based on reason and description.

    Request body:
    {
        "target_type": "case" | "module",
        "target_ids": [1, 3, 5],
        "reason": "reason for regeneration",
        "description": "additional requirements"
    }
    """
    data = request.get_json() or {}
    target_type = data.get("target_type")
    target_ids = data.get("target_ids", [])
    reason = data.get("reason", "").strip()
    description = data.get("description", "").strip()

    if not target_type or target_type not in ("case", "module"):
        return jsonify({"error": "target_type must be 'case' or 'module'"}), 400

    if not target_ids or not isinstance(target_ids, list):
        return jsonify({"error": "target_ids must be a non-empty list"}), 400

    if not reason or not description:
        return jsonify({"error": "reason and description are required"}), 400

    # Validate targets exist and belong to current user
    if target_type == "case":
        existing = TestCase.query.filter(TestCase.id.in_(target_ids)).all()
        for case in existing:
            if not case.module or not case.module.requirement or \
               case.module.requirement.user_id != g.current_user_id:
                return jsonify({"error": "Forbidden: you do not have access to this resource"}), 403
    else:
        existing = Module.query.filter(Module.id.in_(target_ids)).all()
        for module in existing:
            if not module.requirement or module.requirement.user_id != g.current_user_id:
                return jsonify({"error": "Forbidden: you do not have access to this resource"}), 403

    if len(existing) != len(target_ids):
        return jsonify({"error": "Some targets not found"}), 404

    # If single target, run in background thread
    if len(target_ids) == 1:
        target_id = target_ids[0]
        task_id = task_store.create("regen", user_id=g.current_user_id)

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_run_with_app_context(app, case_service.regenerate_task,
                                         target_type, target_id, reason, description,
                                         g.current_user_id, task_id),
            daemon=True,
        )
        thread.start()

        logger.info("Regeneration started: type=%s id=%d task_id=%s", target_type, target_id, task_id)
        return jsonify({
            "task_id": task_id,
            "message": f"Regeneration started for {target_type} {target_id}",
            "target_count": 1,
        })

    # Multiple targets: create one task per target, return all task_ids
    task_ids = []
    app = current_app._get_current_object()
    for target_id in target_ids:
        task_id = task_store.create("regen", user_id=g.current_user_id)

        thread = threading.Thread(
            target=_run_with_app_context(app, case_service.regenerate_task,
                                         target_type, target_id, reason, description,
                                         g.current_user_id, task_id),
            daemon=True,
        )
        thread.start()

        task_ids.append(task_id)

    logger.info("Batch regeneration started: type=%s count=%d", target_type, len(task_ids))

    # Track event
    from app.services.analytics_service import AnalyticsService
    AnalyticsService().track_event(
        user_id=g.current_user_id,
        event_type="regenerate",
        event_data={
            "target_type": target_type,
            "target_count": len(target_ids),
            "reason": reason,
        },
    )

    return jsonify({
        "task_ids": task_ids,
        "message": f"Regeneration started for {len(task_ids)} {target_type}s",
        "target_count": len(task_ids),
    })
