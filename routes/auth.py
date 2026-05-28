from flask import Blueprint, request, jsonify
from flask_security import current_user, login_user, logout_user, hash_password, verify_password
from models import db, User, UserRiskState
import extensions

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if len(username) < 3 or len(username) > 30:
        return jsonify({"error": "Username must be 3–30 characters"}), 400
    if not username.replace("_", "").isalnum():
        return jsonify({"error": "Username can only contain letters, numbers, and underscores"}), 400
    if User.query.filter_by(username=username.lower()).first():
        return jsonify({"error": "Username already exists"}), 409

    extensions.user_datastore.create_user(username=username.lower(), password=hash_password(password))
    db.session.commit()
    return jsonify({"message": "Account created successfully"}), 201


@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    username = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not verify_password(password, user.password):
        return jsonify({"error": "Invalid username or password"}), 401

    login_user(user)
    has_intake = user.intake is not None and user.intake.completed_at is not None
    return jsonify({
        "message": "Logged in",
        "hasCompletedIntake": has_intake,
        "isPro": user.is_pro,
        "token": user.get_auth_token()
    }), 200


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    logout_user()
    return jsonify({"message": "Logged out"}), 200


@auth_bp.route("/api/me", methods=["GET"])
def me():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401
    has_intake = current_user.intake is not None and current_user.intake.completed_at is not None
    return jsonify({
        "username": current_user.username,
        "isPro": current_user.is_pro,
        "hasCompletedIntake": has_intake
    }), 200


@auth_bp.route("/api/account", methods=["DELETE"])
def delete_account():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401
    user = current_user._get_current_object()
    logout_user()
    # UserRiskState has no ORM cascade on the User side — delete it manually first
    # to avoid a foreign-key violation when the user row is removed.
    UserRiskState.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account deleted"}), 200
