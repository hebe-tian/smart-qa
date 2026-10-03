"""Modules blueprint: CRUD operations."""
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.module import Module
from app.core.decorators import token_required
from app.core.ownership import check_module_owner, check_requirement_owner

modules_bp = Blueprint("modules", __name__)


@modules_bp.route("/requirement/<int:req_id>", methods=["GET"])
@token_required
def list_modules(req_id):
    check_requirement_owner(req_id)
    modules = Module.query.filter_by(requirement_id=req_id).order_by(Module.order).all()
    return jsonify({"modules": [m.to_dict() for m in modules]})


@modules_bp.route("/<int:module_id>", methods=["GET"])
@token_required
def get_module(module_id):
    module = check_module_owner(module_id)
    return jsonify(module.to_dict(include_cases=True))


@modules_bp.route("/<int:module_id>", methods=["PUT"])
@token_required
def update_module(module_id):
    module = check_module_owner(module_id)
    data = request.get_json() or {}

    if "name" in data:
        module.name = data["name"].strip()
    if "description" in data:
        module.description = data["description"].strip()
    if "order" in data:
        module.order = data["order"]

    db.session.commit()
    return jsonify(module.to_dict())


@modules_bp.route("/<int:module_id>", methods=["DELETE"])
@token_required
def delete_module(module_id):
    module = check_module_owner(module_id)
    db.session.delete(module)
    db.session.commit()
    return jsonify({"message": "Module deleted"})
