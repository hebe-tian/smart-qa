"""Generate blueprint: async module and case generation via background threads."""
import threading
from flask import Blueprint, request, jsonify, g, current_app
from app.models.requirement import Requirement
from app.models.module import Module
from app.services.task_store import task_store
from app.services.case_service import case_service
from app.core.decorators import token_required
from app.core.ownership import check_requirement_owner, check_module_owner
from app.services.logging_service import get_logger

generate_bp = Blueprint("generate", __name__)
logger = get_logger("api")


def _run_with_app_context(app, func, *args):
    """Run a function in a background thread with Flask application context."""
    def _wrapper():
        with app.app_context():
            func(*args)
    return _wrapper


@generate_bp.route("/modules", methods=["POST"])
@token_required
def generate_modules():
    """Start async module generation. Returns task_id for polling."""
    data = request.get_json() or {}
    requirement_id = data.get("requirement_id")

    req = check_requirement_owner(requirement_id)

    task_id = task_store.create("module_gen", requirement_id=requirement_id, user_id=g.current_user_id)

    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_with_app_context(app, case_service.generate_modules_task,
                                     requirement_id, g.current_user_id, task_id),
        daemon=True,
    )
    thread.start()

    logger.info("Module generation started: req_id=%d task_id=%s", requirement_id, task_id)
    return jsonify({"task_id": task_id, "message": "Module generation started"})


@generate_bp.route("/cases", methods=["POST"])
@token_required
def generate_cases():
    """Start async case generation. Supports single module or all modules."""
    data = request.get_json() or {}
    module_id = data.get("module_id")
    requirement_id = data.get("requirement_id")

    if module_id:
        module = check_module_owner(module_id)
        task_id = task_store.create("case_gen", requirement_id=module.requirement_id, user_id=g.current_user_id)

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_run_with_app_context(app, case_service.generate_cases_task,
                                         module_id, g.current_user_id, task_id),
            daemon=True,
        )
        thread.start()

        logger.info("Case generation started: module_id=%d task_id=%s", module_id, task_id)
        return jsonify({"task_id": task_id, "message": "Case generation started"})

    elif requirement_id:
        req = check_requirement_owner(requirement_id)
        task_id = task_store.create("case_gen_all", requirement_id=requirement_id, user_id=g.current_user_id)

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_run_with_app_context(app, case_service.generate_all_cases_task,
                                         requirement_id, g.current_user_id, task_id),
            daemon=True,
        )
        thread.start()

        logger.info("All case generation started: req_id=%d task_id=%s", requirement_id, task_id)
        return jsonify({"task_id": task_id, "message": "All case generation started"})

    return jsonify({"error": "Either module_id or requirement_id is required"}), 400
