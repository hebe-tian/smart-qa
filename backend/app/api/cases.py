"""Cases blueprint: CRUD operations."""
import json
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.test_case import TestCase
from app.core.decorators import token_required
from app.core.ownership import check_case_owner, check_module_owner

cases_bp = Blueprint("cases", __name__)


@cases_bp.route("/module/<int:module_id>", methods=["GET"])
@token_required
def list_cases(module_id):
    check_module_owner(module_id)
    cases = TestCase.query.filter_by(module_id=module_id).order_by(TestCase.order).all()
    return jsonify({"cases": [c.to_dict() for c in cases]})


@cases_bp.route("/<int:case_id>", methods=["GET"])
@token_required
def get_case(case_id):
    case = check_case_owner(case_id)
    return jsonify(case.to_dict())


@cases_bp.route("/<int:case_id>", methods=["PUT"])
@token_required
def update_case(case_id):
    case = check_case_owner(case_id)
    data = request.get_json() or {}

    if "title" in data:
        case.title = data["title"].strip()
    if "preconditions" in data:
        case.preconditions = data["preconditions"].strip()
    if "steps" in data:
        case.steps_json = json.dumps(data["steps"], ensure_ascii=False)
    if "expected_result" in data:
        case.expected_result = data["expected_result"].strip()
    if "priority" in data:
        case.priority = data["priority"]
    if "case_type" in data:
        case.case_type = data["case_type"]
    if "order" in data:
        case.order = data["order"]

    db.session.commit()
    return jsonify(case.to_dict())


@cases_bp.route("/<int:case_id>", methods=["DELETE"])
@token_required
def delete_case(case_id):
    case = check_case_owner(case_id)
    db.session.delete(case)
    db.session.commit()
    return jsonify({"message": "Case deleted"})
