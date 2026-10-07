"""Ownership verification helpers to prevent unauthorized cross-user access."""
from flask import g, abort
from app.models.requirement import Requirement
from app.models.module import Module
from app.models.test_case import TestCase


def check_requirement_owner(req_id):
    """Get requirement by ID, abort 404 if not found, 403 if not owned by current user.

    Guests (current_user_id is None) may read any requirement (global read-only).
    """
    req = Requirement.query.get_or_404(req_id)
    if g.current_user_id is not None and req.user_id != g.current_user_id:
        abort(403)
    return req


def check_module_owner(module_id):
    """Get module by ID, abort 404 if not found, 403 if parent requirement not owned."""
    module = Module.query.get_or_404(module_id)
    if g.current_user_id is not None and (not module.requirement or module.requirement.user_id != g.current_user_id):
        abort(403)
    return module


def check_case_owner(case_id):
    """Get test case by ID, abort 404 if not found, 403 if parent requirement not owned."""
    case = TestCase.query.get_or_404(case_id)
    if g.current_user_id is not None and (not case.module or not case.module.requirement or case.module.requirement.user_id != g.current_user_id):
        abort(403)
    return case
