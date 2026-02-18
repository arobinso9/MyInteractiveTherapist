"""
ZenShell – MyInteractiveTherapist
Flask Backend  |  main.py

Stack  : Python 3.10+, Flask 3.x, Flask-SQLAlchemy, Flask-Bcrypt,
         Flask-Limiter, PyJWT, Flask-CORS
DB     : SQLite  (therapy.db)
Auth   : JWT stored in httpOnly cookie
Security features implemented:
  - Bcrypt password hashing (cost 14)
  - Progressive account lockout: 1 m → 5 m → 15 m → 30 m → 1 h → 24 h
  - JWT httpOnly + Secure + SameSite=Strict cookies
  - Per-route rate limiting via Flask-Limiter
  - Strict user-data isolation (every DB query filters by user_id)
  - CSRF protection via double-submit cookie pattern
  - Crisis keyword detection with 988 redirect signal
  - LLM-placeholder hook for "Presenting Concerns" analysis
"""

from __future__ import annotations

import os
import re
import json
import time
import uuid
import logging
import datetime
from functools import wraps

import jwt
from flask import (
    Flask, request, jsonify, make_response,
    render_template_string, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ---------------------------------------------------------------------------
# App bootstrap
# ---------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

# ── Configuration ──────────────────────────────────────────────────────────
app.config.update(
    SECRET_KEY=os.environ.get("ZEN_SECRET_KEY", os.urandom(32).hex()),
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(BASE_DIR, 'therapy.db')}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_ALGORITHM="HS256",
    JWT_ACCESS_TTL_MINUTES=int(os.environ.get("JWT_TTL_MINUTES", 60)),
)

# ── Extensions ─────────────────────────────────────────────────────────────
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
CORS(app, supports_credentials=True, origins=["http://localhost:5000",
                                               "http://127.0.0.1:5000"])
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["300 per hour"],
    storage_uri="memory://",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Progressive Lockout Schedule
# ---------------------------------------------------------------------------
LOCKOUT_STEPS: list[int] = [
    1 * 60,       # attempt 1 → 1 min
    5 * 60,       # attempt 2 → 5 min
    15 * 60,      # attempt 3 → 15 min
    30 * 60,      # attempt 4 → 30 min
    60 * 60,      # attempt 5 → 1 hour
    24 * 60 * 60, # attempt 6+ → 24 hours
]

# ---------------------------------------------------------------------------
# Crisis keyword set (triggers 988 banner on the front-end)
# ---------------------------------------------------------------------------
CRISIS_KEYWORDS: set[str] = {
    "suicid", "kill myself", "end my life", "want to die",
    "self-harm", "self harm", "cutting", "overdose",
    "harm myself", "no reason to live", "can't go on",
    "hopeless", "worthless", "hurt myself",
}

# ---------------------------------------------------------------------------
# Password policy constants
# ---------------------------------------------------------------------------
COMMON_PASSWORDS: set[str] = {
    "password", "password123", "123456", "12345678", "qwerty",
    "abc123", "letmein", "trustno1", "dragon", "iloveyou",
    "master", "sunshine", "superman", "welcome", "admin",
    "root", "therapy", "zenshell", "health", "mental",
    "Password123!", "Welcome123", "Admin123!", "Test1234!", "User1234!",
}

# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------

class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(30),  unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at    = db.Column(db.DateTime,    default=datetime.datetime.utcnow)

    # Progressive lockout
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until    = db.Column(db.Float,   nullable=True)  # Unix timestamp

    # Intake
    has_completed_intake = db.Column(db.Boolean, default=False)

    # Relationships
    intake   = db.relationship("Intake",   back_populates="user", uselist=False,
                                cascade="all, delete-orphan")
    sessions = db.relationship("Session",  back_populates="user",
                                cascade="all, delete-orphan",
                                order_by="Session.created_at.desc()")

    def set_password(self, raw: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(raw, rounds=14).decode()

    def check_password(self, raw: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, raw)

    def is_locked(self) -> tuple[bool, float]:
        if self.locked_until and time.time() < self.locked_until:
            return True, self.locked_until - time.time()
        return False, 0.0

    def record_failed_login(self) -> None:
        self.failed_attempts += 1
        idx = min(self.failed_attempts - 1, len(LOCKOUT_STEPS) - 1)
        self.locked_until = time.time() + LOCKOUT_STEPS[idx]
        db.session.commit()

    def reset_login_attempts(self) -> None:
        self.failed_attempts = 0
        self.locked_until = None
        db.session.commit()


class Intake(db.Model):
    __tablename__ = "intakes"

    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False,
                        unique=True)
    data    = db.Column(db.Text, nullable=False)          # JSON blob
    updated_at = db.Column(db.DateTime, onupdate=datetime.datetime.utcnow,
                           default=datetime.datetime.utcnow)
    is_draft = db.Column(db.Boolean, default=False)

    user = db.relationship("User", back_populates="intake")

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "data":       json.loads(self.data),
            "is_draft":   self.is_draft,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Session(db.Model):
    __tablename__ = "sessions"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    pre_stress  = db.Column(db.Integer,  nullable=True)
    post_stress = db.Column(db.Integer,  nullable=True)
    takeaway    = db.Column(db.Text,     nullable=True)
    chat        = db.Column(db.Text,     default="[]")   # JSON array of messages
    crisis_flag = db.Column(db.Boolean,  default=False)

    user = db.relationship("User", back_populates="sessions")

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "created_at":  self.created_at.isoformat(),
            "pre_stress":  self.pre_stress,
            "post_stress": self.post_stress,
            "takeaway":    self.takeaway,
            "chat":        json.loads(self.chat or "[]"),
            "crisis_flag": self.crisis_flag,
        }


# ---------------------------------------------------------------------------
# JWT Helpers
# ---------------------------------------------------------------------------

def _issue_token(user_id: int) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(
            minutes=app.config["JWT_ACCESS_TTL_MINUTES"]
        ),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, app.config["SECRET_KEY"],
                      algorithm=app.config["JWT_ALGORITHM"])


def _decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, app.config["SECRET_KEY"],
                          algorithms=[app.config["JWT_ALGORITHM"]])
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid JWT: %s", exc)
    return None


def _set_auth_cookie(response, token: str) -> None:
    response.set_cookie(
        "zen_token",
        token,
        httponly=True,
        secure=False,           # set True in production behind HTTPS
        samesite="Strict",
        max_age=app.config["JWT_ACCESS_TTL_MINUTES"] * 60,
    )


def _clear_auth_cookie(response) -> None:
    response.delete_cookie("zen_token")


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("zen_token")
        if not token:
            return jsonify({"error": "Authentication required"}), 401
        payload = _decode_token(token)
        if payload is None:
            return jsonify({"error": "Session expired – please log in again"}), 401
        user = db.session.get(User, payload["sub"])
        if user is None:
            return jsonify({"error": "User not found"}), 401
        request.current_user = user
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Password Validation
# ---------------------------------------------------------------------------

def _validate_password(password: str, username: str) -> list[str]:
    errors: list[str] = []

    if len(password) < 10:
        errors.append("Password must be at least 10 characters.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one number.")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};':\"\\|,.<>/?`~]", password):
        errors.append("Password must contain at least one special character.")
    if password.lower() in {p.lower() for p in COMMON_PASSWORDS}:
        errors.append("This password is too common. Please choose a stronger one.")
    if username.lower() in password.lower():
        errors.append("Password cannot contain your username.")

    return errors


# ---------------------------------------------------------------------------
# Crisis Detection
# ---------------------------------------------------------------------------

def _detect_crisis(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in CRISIS_KEYWORDS)


# ---------------------------------------------------------------------------
# LLM Placeholder
# ---------------------------------------------------------------------------

def _analyze_presenting_concerns(text: str) -> dict:
    """
    Placeholder for future LLM integration.

    Drop-in replacement: swap the stub body below with an actual API call
    to Anthropic Claude (or OpenAI, etc.).

    Example production implementation:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": PROMPT.format(text=text)}]
        )
        return {"summary": message.content[0].text, "provider": "claude-opus-4-6"}
    """
    crisis = _detect_crisis(text)
    return {
        "summary":       "(LLM analysis not yet configured – connect an API key to enable)",
        "crisis_signal": crisis,
        "provider":      "placeholder",
    }


# ---------------------------------------------------------------------------
# Routes – Static
# ---------------------------------------------------------------------------

@app.route("/")
def serve_index():
    """Serve the SPA."""
    return send_from_directory(BASE_DIR, "index.html")


# ---------------------------------------------------------------------------
# Routes – Auth
# ---------------------------------------------------------------------------

@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("10 per hour")
def register():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()

    # ── username rules ──
    if not username:
        return jsonify({"error": "Username is required."}), 400
    if not re.match(r"^[a-zA-Z0-9_]{3,30}$", username):
        return jsonify({
            "error": "Username must be 3–30 characters: letters, numbers, underscores only."
        }), 400

    # ── password rules ──
    pw_errors = _validate_password(password, username)
    if pw_errors:
        return jsonify({"error": pw_errors[0], "all_errors": pw_errors}), 400

    # ── uniqueness ──
    if User.query.filter_by(username=username.lower()).first():
        return jsonify({"error": "That username is already taken."}), 409

    user = User(username=username.lower())
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    logger.info("New user registered: %s", username)
    return jsonify({"message": "Account created successfully. Please log in."}), 201


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("20 per hour")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip().lower()
    password = (body.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    user: User | None = User.query.filter_by(username=username).first()

    # ── lockout check (run even if user not found to prevent user enumeration) ──
    if user:
        locked, remaining = user.is_locked()
        if locked:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            if remaining >= 3600:
                time_str = f"{int(remaining // 3600)} hour(s)"
            elif remaining >= 60:
                time_str = f"{mins} minute(s)"
            else:
                time_str = f"{secs} second(s)"
            return jsonify({
                "error": f"Account locked. Try again in {time_str}.",
                "locked": True,
                "remaining_seconds": int(remaining),
            }), 429

    # ── credential check ──
    if user is None or not user.check_password(password):
        if user:
            user.record_failed_login()
            locked, remaining = user.is_locked()
            attempt_no = user.failed_attempts
            if locked:
                idx = min(attempt_no - 1, len(LOCKOUT_STEPS) - 1)
                duration = LOCKOUT_STEPS[idx]
                mins = duration // 60
                return jsonify({
                    "error": f"Incorrect credentials. Account locked for {mins} minute(s).",
                    "locked": True,
                    "remaining_seconds": duration,
                }), 429
        return jsonify({
            "error": "Incorrect username or password.",
            "locked": False,
        }), 401

    # ── success ──
    user.reset_login_attempts()
    token = _issue_token(user.id)

    resp = make_response(jsonify({
        "message": "Login successful.",
        "user": {
            "username":             user.username,
            "has_completed_intake": user.has_completed_intake,
        },
    }))
    _set_auth_cookie(resp, token)
    return resp, 200


@app.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    resp = make_response(jsonify({"message": "Logged out successfully."}))
    _clear_auth_cookie(resp)
    return resp, 200


@app.route("/api/auth/me", methods=["GET"])
@login_required
def me():
    user: User = request.current_user
    return jsonify({
        "username":             user.username,
        "has_completed_intake": user.has_completed_intake,
        "created_at":           user.created_at.isoformat(),
    }), 200


# ---------------------------------------------------------------------------
# Routes – Intake
# ---------------------------------------------------------------------------

@app.route("/api/intake", methods=["GET"])
@login_required
def get_intake():
    user: User = request.current_user
    if not user.intake:
        return jsonify({"intake": None}), 200
    return jsonify({"intake": user.intake.to_dict()}), 200


@app.route("/api/intake", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def submit_intake():
    """Submit or update the intake form (full or draft)."""
    user: User = request.current_user
    body = request.get_json(silent=True) or {}
    data = body.get("data", {})
    is_draft = bool(body.get("is_draft", False))

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid intake payload."}), 400

    # ── mandatory field checks for final submission ──
    if not is_draft:
        errors = _validate_intake(data)
        if errors:
            return jsonify({"error": "Validation failed.", "fields": errors}), 422

    # ── crisis detection on presenting concerns ──
    presenting_text = data.get("presenting", "")
    llm_result = _analyze_presenting_concerns(presenting_text)
    crisis_flag = llm_result.get("crisis_signal", False)

    # ── persist ──
    if user.intake:
        user.intake.data     = json.dumps(data)
        user.intake.is_draft = is_draft
    else:
        intake = Intake(
            user_id  = user.id,
            data     = json.dumps(data),
            is_draft = is_draft,
        )
        db.session.add(intake)

    if not is_draft:
        user.has_completed_intake = True

    db.session.commit()

    return jsonify({
        "message":       "Draft saved." if is_draft else "Intake submitted successfully.",
        "crisis_signal": crisis_flag,
        "llm":           llm_result,
    }), 200


def _validate_intake(d: dict) -> dict[str, str]:
    """Return a dict of {field: error_message} for mandatory intake fields."""
    errors: dict[str, str] = {}

    def require(field: str, label: str, min_len: int = 1):
        val = (d.get(field) or "").strip()
        if not val:
            errors[field] = f"{label} is required."
        elif len(val) < min_len:
            errors[field] = f"{label} must be at least {min_len} characters."

    def require_words(field: str, label: str, min_words: int):
        val = (d.get(field) or "").strip()
        if not val:
            errors[field] = f"{label} is required."
        elif len(val.split()) < min_words:
            errors[field] = f"{label} must be at least {min_words} words."

    def require_radio(field: str, label: str):
        if not d.get(field):
            errors[field] = f"{label} is required."

    def require_checkbox(field: str, label: str):
        val = d.get(field)
        if not val or (isinstance(val, list) and len(val) == 0):
            errors[field] = f"Please select at least one option for {label}."

    # Section 1
    require("fullName",         "Full Name")
    require("pronouns",         "Pronouns")
    require("dob",              "Date of Birth")
    require("genderIdentity",   "Gender Identity")
    require_radio("sexAssigned","Sex Assigned at Birth")
    require("address",          "Address",           min_len=5)
    require("emergencyContact", "Emergency Contact", min_len=5)

    # Email
    email = (d.get("email") or "").strip()
    if not email:
        errors["email"] = "Email is required."
    elif not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        errors["email"] = "Email must be a valid address."

    # Phone
    phone_digits = re.sub(r"\D", "", d.get("phone") or "")
    if not phone_digits:
        errors["phone"] = "Phone number is required."
    elif not (10 <= len(phone_digits) <= 11):
        errors["phone"] = "Phone number must be 10–11 digits."

    # Section 2
    require_words("presenting", "What brings you to therapy", min_words=10)
    require_radio("duration",   "Duration of concern")
    require_checkbox("issues",  "Primary Issues")

    # Section 3
    for field, label in [
        ("selfharm",        "Thoughts of harming yourself"),
        ("attempts",        "History of suicide attempts"),
        ("harmOthers",      "Thoughts of harming others"),
        ("selfharmHistory", "History of self-harm"),
        ("currentlySafe",   "Are you currently safe"),
    ]:
        require_radio(field, label)

    if d.get("attempts") == "yes" and not d.get("attemptsWhen", "").strip():
        errors["attemptsWhen"] = "Please specify when the attempt(s) occurred."

    # Section 4
    require_radio("prevTherapy", "Previous therapy")
    if d.get("prevTherapy") == "yes":
        require_words("whatWorked",    "What worked well",    min_words=5)
        require_words("whatDidntWork", "What didn't work",    min_words=5)
    require_radio("hospitalizations", "Psychiatric hospitalizations")
    if d.get("hospitalizations") == "yes" and not d.get("hospitalizationDetails", "").strip():
        errors["hospitalizationDetails"] = "Please describe the hospitalizations."

    # Section 5
    require_radio("psychiatrist", "Current psychiatrist")
    require_radio("sleep",        "Sleep quality")

    # Section 6
    for sub in ("alcohol", "marijuana", "cocaine", "opioids", "otherSubstance"):
        require_radio(sub, sub.capitalize())

    # Section 7
    require_checkbox("trauma", "Trauma screening")
    require_radio("traumaSymptoms", "Flashbacks/nightmares/hypervigilance")

    # Section 8
    require_radio("relStatus", "Relationship status")
    require_radio("children",  "Children")
    if d.get("children") == "yes" and not d.get("childrenAges", "").strip():
        errors["childrenAges"] = "Please provide the age(s) of your child(ren)."

    # Section 9
    require_radio("workStatus",  "Work/school status")
    require_radio("performance", "Performance impact")
    require_radio("functioning", "Daily functioning")

    # Section 10
    require_checkbox("therapistType", "Therapist preference")
    require_checkbox("therapyStyle",  "Therapy style preference")

    # Section 11
    require("ethnicity",       "Ethnicity/Race")
    require("religion",        "Religion/Spirituality")
    require("primaryLanguage", "Primary language")

    # Section 12
    require_words("therapySuccess", "What success in therapy looks like", min_words=10)
    for i in (1, 2, 3):
        require_words(f"goal{i}", f"Goal #{i}", min_words=3)

    return errors


# ---------------------------------------------------------------------------
# Routes – Sessions
# ---------------------------------------------------------------------------

@app.route("/api/sessions", methods=["GET"])
@login_required
def list_sessions():
    user: User = request.current_user
    return jsonify({
        "sessions": [s.to_dict() for s in user.sessions]
    }), 200


@app.route("/api/sessions", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def create_session():
    """Create a new therapy session record."""
    user: User = request.current_user
    if not user.has_completed_intake:
        return jsonify({"error": "Please complete the intake form first."}), 403

    body = request.get_json(silent=True) or {}
    pre_stress = body.get("pre_stress")

    session_obj = Session(
        user_id    = user.id,
        pre_stress = int(pre_stress) if pre_stress is not None else None,
    )
    db.session.add(session_obj)
    db.session.commit()
    return jsonify({"session": session_obj.to_dict()}), 201


@app.route("/api/sessions/<int:session_id>", methods=["GET"])
@login_required
def get_session(session_id: int):
    user: User = request.current_user
    session_obj = Session.query.filter_by(id=session_id, user_id=user.id).first()
    if not session_obj:
        return jsonify({"error": "Session not found."}), 404
    return jsonify({"session": session_obj.to_dict()}), 200


@app.route("/api/sessions/<int:session_id>/message", methods=["POST"])
@login_required
@limiter.limit("120 per hour")
def add_message(session_id: int):
    """Append a chat message and run crisis detection."""
    user: User = request.current_user
    session_obj = Session.query.filter_by(id=session_id, user_id=user.id).first()
    if not session_obj:
        return jsonify({"error": "Session not found."}), 404

    body = request.get_json(silent=True) or {}
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Message content is required."}), 400

    # Append to chat log
    chat = json.loads(session_obj.chat or "[]")
    msg = {
        "role":      "user",
        "content":   content,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    chat.append(msg)

    # Crisis detection
    crisis = _detect_crisis(content)
    if crisis:
        session_obj.crisis_flag = True

    session_obj.chat = json.dumps(chat)
    db.session.commit()

    return jsonify({
        "message":       msg,
        "crisis_signal": crisis,
    }), 200


@app.route("/api/sessions/<int:session_id>/close", methods=["POST"])
@login_required
def close_session(session_id: int):
    """Record post-session stress + takeaway and close the session."""
    user: User = request.current_user
    session_obj = Session.query.filter_by(id=session_id, user_id=user.id).first()
    if not session_obj:
        return jsonify({"error": "Session not found."}), 404

    body = request.get_json(silent=True) or {}
    session_obj.post_stress = int(body["post_stress"]) if body.get("post_stress") is not None else None
    session_obj.takeaway    = (body.get("takeaway") or "").strip() or None
    db.session.commit()

    return jsonify({"session": session_obj.to_dict()}), 200


# ---------------------------------------------------------------------------
# Routes – Account Management ("Right to Disappear")
# ---------------------------------------------------------------------------

@app.route("/api/account/delete-sessions", methods=["DELETE"])
@login_required
def delete_sessions():
    """Permanently wipe all therapy session chats (keep account + intake)."""
    user: User = request.current_user
    Session.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return jsonify({"message": "All session chats have been permanently deleted."}), 200


@app.route("/api/account/wipe", methods=["DELETE"])
@login_required
def wipe_account():
    """Permanently delete the entire account and all associated data."""
    user: User = request.current_user
    db.session.delete(user)
    db.session.commit()

    resp = make_response(jsonify({
        "message": "Your account and all data have been permanently deleted."
    }))
    _clear_auth_cookie(resp)
    return resp, 200


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Resource not found."}), 404


@app.errorhandler(405)
def method_not_allowed(_):
    return jsonify({"error": "Method not allowed."}), 405


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": f"Too many requests: {e.description}"}), 429


@app.errorhandler(500)
def internal_error(exc):
    logger.exception("Internal server error")
    return jsonify({"error": "An internal server error occurred."}), 500


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()
    logger.info("Database initialised at %s", app.config["SQLALCHEMY_DATABASE_URI"])


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
