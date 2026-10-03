"""Auth blueprint: login and register."""
import time
from collections import defaultdict
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.user import User
from app.core.security import generate_token
from app.core.decorators import token_required
from app.config import Config
from app.services.logging_service import get_logger

auth_bp = Blueprint("auth", __name__)
logger = get_logger("auth")

# Simple in-memory rate limiter for registration: {ip: [timestamps]}
_registration_attempts = defaultdict(list)
_REGISTRATION_WINDOW = 3600  # 1 hour
_REGISTRATION_MAX = 5  # max 5 registrations per IP per hour


def _check_registration_rate_limit(ip):
    """Simple in-memory rate limiter. Returns True if allowed, False if rate-limited."""
    now = time.time()
    attempts = _registration_attempts[ip]
    # Prune old entries
    _registration_attempts[ip] = [t for t in attempts if now - t < _REGISTRATION_WINDOW]
    if len(_registration_attempts[ip]) >= _REGISTRATION_MAX:
        return False
    _registration_attempts[ip].append(now)
    return True


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        logger.warning("Login failed for user: %s", username)
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(user.id, user.username)
    logger.info("User logged in: %s (id=%d)", user.username, user.id)

    # Track login event
    from app.services.analytics_service import AnalyticsService
    AnalyticsService().track_event(
        user_id=user.id,
        event_type="login",
        page_url="/",
        ip_address=request.remote_addr,
        ua=request.headers.get("User-Agent", ""),
    )

    return jsonify({"token": token, "user": user.to_dict()})


@auth_bp.route("/guest", methods=["POST"])
def guest_login():
    """One-click guest login: issue a read-only guest token (no DB user)."""
    token = generate_token(None, "游客", role="guest")
    logger.info("Guest session started")

    # Track guest login event (user_id stays null for guests)
    from app.services.analytics_service import AnalyticsService
    AnalyticsService().track_event(
        user_id=None,
        event_type="guest_login",
        page_url="/",
        ip_address=request.remote_addr,
        ua=request.headers.get("User-Agent", ""),
    )

    return jsonify({"token": token, "user": {"username": "游客", "role": "guest"}})


@auth_bp.route("/register", methods=["POST"])
def register():
    if not Config.REGISTRATION_ENABLED:
        return jsonify({"error": "Registration is disabled. Please contact the administrator."}), 403

    client_ip = request.remote_addr or "unknown"
    if not _check_registration_rate_limit(client_ip):
        return jsonify({"error": "Too many registration attempts. Please try again later."}), 429

    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    logger.info("User registered: %s (id=%d)", user.username, user.id)
    token = generate_token(user.id, user.username)
    return jsonify({"token": token, "user": user.to_dict()}), 201


@auth_bp.route("/me", methods=["GET"])
@token_required
def me():
    user = User.query.get(g.current_user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user.to_dict()})
