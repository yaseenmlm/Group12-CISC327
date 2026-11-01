from flask import Blueprint, jsonify, request

from app import store
from app.models.member import Member

members_bp = Blueprint("members", __name__, url_prefix="/members")


@members_bp.route("", methods=["GET"])
def list_members():
    results = list(store.members.values())
    search = request.args.get("search", "").strip().lower()
    if search:
        results = [m for m in results if search in m.name.lower()]
    return jsonify([m.to_dict() for m in results])


@members_bp.route("", methods=["POST"])
def create_member():
    data = request.get_json()
    member_id = store.next_id("member")
    member = Member(id=member_id, name=data["name"], email=data["email"])
    store.members[member_id] = member
    return jsonify(member.to_dict()), 201


@members_bp.route("/<int:member_id>", methods=["GET"])
def get_member(member_id):
    member = store.members.get(member_id)
    if member is None:
        return jsonify({"error": "Member not found"}), 404
    return jsonify(member.to_dict())


@members_bp.route("/<int:member_id>", methods=["PUT"])
def update_member(member_id):
    member = store.members.get(member_id)
    if member is None:
        return jsonify({"error": "Member not found"}), 404
    data = request.get_json()
    member.name = data.get("name", member.name)
    member.email = data.get("email", member.email)
    return jsonify(member.to_dict())


@members_bp.route("/<int:member_id>", methods=["DELETE"])
def delete_member(member_id):
    member = store.members.pop(member_id, None)
    if member is None:
        return jsonify({"error": "Member not found"}), 404
    return "", 204
