import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm.attributes import flag_modified
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ============================================
# CONFIG
# ============================================
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
# Render gives postgres:// but SQLAlchemy requires postgresql://
_db_url = os.getenv("DATABASE_URL", "sqlite:///zenshell.db")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") != "development"

# ============================================
# EXTENSIONS
# ============================================
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)

_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

client = OpenAI(api_key=_api_key)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# ============================================
# MODELS
# ============================================
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id              = db.Column(db.Integer, primary_key=True)
    username        = db.Column(db.String(30), unique=True, nullable=False)
    password_hash   = db.Column(db.String(128), nullable=False)
    is_pro          = db.Column(db.Boolean, default=False)
    mfa_enabled     = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    intake              = db.relationship("IntakeProfile",       backref="user", uselist=False, cascade="all, delete-orphan")
    guardian            = db.relationship("GuardianProfile",     backref="user", uselist=False, cascade="all, delete-orphan")
    sessions            = db.relationship("TherapySession",      backref="user", lazy=True,     cascade="all, delete-orphan")
    assignments         = db.relationship("Assignment",          backref="user", lazy=True,     cascade="all, delete-orphan")
    journal_entries     = db.relationship("JournalEntry",        backref="user", lazy=True,     cascade="all, delete-orphan")
    safety_alerts       = db.relationship("SafetyAlert",         backref="user", lazy=True,     cascade="all, delete-orphan")
    analytics_snapshots = db.relationship("AnalyticsSnapshot",   backref="user", lazy=True,     cascade="all, delete-orphan")


class GuardianProfile(db.Model):
    __tablename__ = "guardian_profiles"
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name                = db.Column(db.String(100))
    email               = db.Column(db.String(120))
    relationship        = db.Column(db.String(50))
    alert_preferences   = db.Column(db.JSON)


class IntakeProfile(db.Model):
    __tablename__ = "intake_profiles"
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    data         = db.Column(db.JSON, nullable=False)
    completed_at = db.Column(db.DateTime)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TherapySession(db.Model):
    __tablename__ = "therapy_sessions"
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    started_at          = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at        = db.Column(db.DateTime)
    initial_mood        = db.Column(db.Integer)
    primary_goal        = db.Column(db.Text)
    final_mood          = db.Column(db.Integer)
    what_worked         = db.Column(db.Text)
    feelings_post       = db.Column(db.Text)
    modality_used       = db.Column(db.String(20))   # CBT / DBT / ACT
    effectiveness_score = db.Column(db.Float)
    summary             = db.Column(db.Text)
    embedding           = db.Column(db.Text)          # placeholder for future pgvector

    messages            = db.relationship("ChatMessage", backref="session", lazy=True, cascade="all, delete-orphan")
    alerts              = db.relationship("SafetyAlert", backref="session", lazy=True, cascade="all, delete-orphan")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id          = db.Column(db.Integer, primary_key=True)
    session_id  = db.Column(db.Integer, db.ForeignKey("therapy_sessions.id"), nullable=False)
    role        = db.Column(db.String(10), nullable=False)   # "user" or "assistant"
    content     = db.Column(db.Text, nullable=False)
    timestamp   = db.Column(db.DateTime, default=datetime.utcnow)


class Assignment(db.Model):
    __tablename__ = "assignments"
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id   = db.Column(db.Integer, db.ForeignKey("therapy_sessions.id", ondelete="SET NULL"))
    title        = db.Column(db.String(100), nullable=False)
    description  = db.Column(db.Text)
    status       = db.Column(db.String(20), default="assigned")  # assigned / in_progress / completed
    due_date     = db.Column(db.DateTime)
    feedback     = db.Column(db.Text)
    completed_at = db.Column(db.DateTime)


class JournalEntry(db.Model):
    __tablename__ = "journal_entries"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    image_url  = db.Column(db.String(500))   # for future handwritten upload
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SafetyAlert(db.Model):
    __tablename__ = "safety_alerts"
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id     = db.Column(db.Integer, db.ForeignKey("therapy_sessions.id"))
    trigger_phrase = db.Column(db.Text)
    severity_level = db.Column(db.String(10))   # LOW / MEDIUM / CRITICAL
    timestamp      = db.Column(db.DateTime, default=datetime.utcnow)
    notified_at    = db.Column(db.DateTime)
    action_taken   = db.Column(db.Text)
    resolved       = db.Column(db.Boolean, default=False)


class AnalyticsSnapshot(db.Model):
    __tablename__ = "analytics_snapshots"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    week_start = db.Column(db.DateTime)
    data       = db.Column(db.JSON)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


ALLOWED_ROLES = {"user", "assistant"}


def build_system_prompt(intake: dict) -> str:
    name = intake.get("preferredName") or intake.get("fullName") or "the client"
    concern = intake.get("presenting") or "not specified"
    goals = "; ".join(filter(None, [intake.get("goal1"), intake.get("goal2"), intake.get("goal3")])) or "not specified"
    issues = ", ".join(intake.get("issues") or []) or "not specified"
    therapist_type = ", ".join(intake.get("therapistType") or []) or "no preference"
    therapy_style = ", ".join(intake.get("therapyStyle") or []) or "no preference"

    return f"""You are a compassionate, professional AI therapist conducting a therapy session with {name}.

Client Information:
- Presenting concern: {concern}
- Primary issues: {issues}
- Therapy goals: {goals}
- Preferred therapist style: {therapist_type}
- Preferred therapy approach: {therapy_style}

Guidelines:
- Be warm, empathetic, and non-judgmental at all times
- Use evidence-based techniques (CBT, DBT, motivational interviewing) as appropriate
- Ask one focused follow-up question per response
- Keep responses concise: 2–4 sentences typically
- Refer to the client by their preferred name when appropriate
- Never diagnose conditions or prescribe medication
- If the client expresses crisis, suicidal ideation, or immediate danger, immediately provide:
  "988 Suicide & Crisis Lifeline (call or text 988)" and "Crisis Text Line: text HOME to 741741"
  and encourage them to reach out now."""


# TODO: Replace detect_crisis() with dedicated safety AI scanner
# Current keyword matching is a placeholder only
CRISIS_PHRASES = {
    "CRITICAL": ["kill myself", "end my life", "want to die", "suicide", "i have a plan", "going to hurt myself"],
    "MEDIUM":   ["hurt myself", "self harm", "cutting", "don't want to be here", "wish i was dead"],
    "LOW":      ["hopeless", "can't go on", "no point", "give up"]
}

def detect_crisis(text):
    lower = text.lower()
    for severity, phrases in CRISIS_PHRASES.items():
        if any(p in lower for p in phrases):
            return severity, next(p for p in phrases if p in lower)
    return None, None


# ============================================
# CREATE TABLES
# ============================================
with app.app_context():
    db.create_all()


# ============================================
# AUTH ENDPOINTS
# ============================================
@app.route("/api/signup", methods=["POST"])
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

    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(username=username.lower(), password_hash=password_hash)
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "Account created successfully"}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    username = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid username or password"}), 401

    login_user(user)
    has_intake = user.intake is not None and user.intake.completed_at is not None
    return jsonify({"message": "Logged in", "hasCompletedIntake": has_intake, "isPro": user.is_pro}), 200


@app.route("/api/logout", methods=["POST"])
def logout():
    logout_user()
    return jsonify({"message": "Logged out"}), 200


@app.route("/api/account", methods=["DELETE"])
def delete_account():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    user = current_user
    logout_user()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account deleted"}), 200


@app.route("/api/me", methods=["GET"])
def me():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    has_intake = current_user.intake is not None and current_user.intake.completed_at is not None
    return jsonify({
        "username": current_user.username,
        "isPro": current_user.is_pro,
        "hasCompletedIntake": has_intake
    }), 200


# ============================================
# INTAKE ENDPOINTS
# ============================================
@app.route("/api/intake", methods=["GET"])
def get_intake():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    if not current_user.intake:
        return jsonify({"error": "No intake found"}), 404

    return jsonify({
        "data": current_user.intake.data,
        "completedAt": current_user.intake.completed_at.isoformat() if current_user.intake.completed_at else None
    }), 200


@app.route("/api/intake", methods=["POST"])
def save_intake():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    body = request.get_json(silent=True)
    if not body or "data" not in body:
        return jsonify({"error": "Intake data is required"}), 400

    completed = body.get("completed", False)

    if current_user.intake:
        # Update existing
        current_user.intake.data = body["data"]
        flag_modified(current_user.intake, "data")
        if completed:
            current_user.intake.completed_at = datetime.utcnow()
    else:
        # Create new
        intake = IntakeProfile(
            user_id=current_user.id,
            data=body["data"],
            completed_at=datetime.utcnow() if completed else None
        )
        db.session.add(intake)

    db.session.commit()
    return jsonify({"message": "Intake saved"}), 200


# ============================================
# SESSION ENDPOINTS
# ============================================
@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    sessions = TherapySession.query.filter_by(user_id=current_user.id)\
        .order_by(TherapySession.started_at.desc()).all()

    return jsonify([{
        "id": s.id,
        "startedAt": s.started_at.isoformat(),
        "completedAt": s.completed_at.isoformat() if s.completed_at else None,
        "initialMood": s.initial_mood,
        "finalMood": s.final_mood,
        "primaryGoal": s.primary_goal,
        "takeaway": s.what_worked,
        "summary": s.summary,
        "modalityUsed": s.modality_used
    } for s in sessions]), 200


@app.route("/api/sessions", methods=["DELETE"])
def delete_all_sessions():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    sessions = TherapySession.query.filter_by(user_id=current_user.id).all()
    for session in sessions:
        db.session.delete(session)
    db.session.commit()
    return jsonify({"message": "All sessions deleted"}), 200


@app.route("/api/sessions", methods=["POST"])
def start_session():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid request body"}), 400

    session = TherapySession(
        user_id=current_user.id,
        initial_mood=body.get("initialMood"),
        primary_goal=body.get("primaryGoal", "")
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({"sessionId": session.id}), 201


@app.route("/api/sessions/<int:session_id>/complete", methods=["POST"])
def complete_session(session_id):
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    session = TherapySession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        return jsonify({"error": "Session not found"}), 404

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid request body"}), 400

    session.final_mood      = body.get("finalMood")
    session.what_worked     = body.get("whatWorked", "")
    session.feelings_post   = body.get("feelingsPost", "")
    session.completed_at    = datetime.utcnow()

    # Generate GPT summary of the conversation
    messages = ChatMessage.query.filter_by(session_id=session_id)\
        .order_by(ChatMessage.timestamp).all()

    if messages:
        transcript = "\n".join([f"{m.role.upper()}: {m.content}" for m in messages])
        try:
            summary_response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "You are summarizing a therapy session. Write a concise 2-3 sentence summary of the key themes, progress, and any concerns discussed. Be clinical but compassionate."},
                    {"role": "user", "content": f"Summarize this session:\n\n{transcript}"}
                ],
                max_tokens=150,
                temperature=0.5
            )
            session.summary = summary_response.choices[0].message.content
        except Exception:
            session.summary = "Summary unavailable."

    db.session.commit()
    return jsonify({"message": "Session completed", "summary": session.summary}), 200


@app.route("/api/sessions/<int:session_id>", methods=["GET"])
def get_session(session_id):
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    session = TherapySession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not session:
        return jsonify({"error": "Session not found"}), 404

    messages = ChatMessage.query.filter_by(session_id=session_id)\
        .order_by(ChatMessage.timestamp).all()

    return jsonify({
        "id": session.id,
        "startedAt": session.started_at.isoformat(),
        "completedAt": session.completed_at.isoformat() if session.completed_at else None,
        "initialMood": session.initial_mood,
        "finalMood": session.final_mood,
        "primaryGoal": session.primary_goal,
        "summary": session.summary,
        "messages": [{"role": m.role, "content": m.content} for m in messages]
    }), 200


# ============================================
# JOURNAL ENDPOINTS
# ============================================
@app.route("/api/journal", methods=["POST"])
def save_journal():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    body = request.get_json(silent=True)
    if not body or not body.get("content", "").strip():
        return jsonify({"error": "Journal content is required"}), 400

    entry = JournalEntry(
        user_id=current_user.id,
        content=body["content"].strip()
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({"message": "Journal entry saved", "id": entry.id}), 201


@app.route("/api/journal", methods=["GET"])
def get_journal():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    entries = JournalEntry.query.filter_by(user_id=current_user.id)\
        .order_by(JournalEntry.created_at.desc()).all()

    return jsonify([{
        "id": e.id,
        "content": e.content,
        "createdAt": e.created_at.isoformat()
    } for e in entries]), 200


# ============================================
# SAFETY TRIGGER ENDPOINT
# ============================================
@app.route("/api/safety-trigger", methods=["POST"])
def safety_trigger():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid request body"}), 400

    severity = body.get("severityLevel", "LOW").upper()
    if severity not in ("LOW", "MEDIUM", "CRITICAL"):
        severity = "LOW"

    alert = SafetyAlert(
        user_id=current_user.id,
        session_id=body.get("sessionId"),
        trigger_phrase=body.get("triggerPhrase", ""),
        severity_level=severity,
        action_taken=body.get("actionTaken", "")
    )
    db.session.add(alert)

    # Mark notified_at if CRITICAL and guardian exists
    # (actual email sending to be wired up with SendGrid later)
    if severity == "CRITICAL" and current_user.guardian:
        alert.notified_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "message": "Safety alert logged",
        "severity": severity,
        "guardianNotified": alert.notified_at is not None
    }), 201


# ============================================
# REPORTS ENDPOINT
# ============================================
@app.route("/api/reports", methods=["GET"])
def get_reports():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    sessions = TherapySession.query.filter(
        TherapySession.user_id == current_user.id,
        TherapySession.completed_at.isnot(None)
    ).order_by(TherapySession.started_at).all()

    total_sessions = len(sessions)
    initial_moods = [s.initial_mood for s in sessions if s.initial_mood is not None]
    final_moods   = [s.final_mood   for s in sessions if s.final_mood   is not None]
    avg_initial     = round(sum(initial_moods) / len(initial_moods), 1) if initial_moods else None
    avg_final       = round(sum(final_moods)   / len(final_moods),   1) if final_moods   else None
    avg_improvement = round(avg_initial - avg_final, 1) if avg_initial is not None and avg_final is not None else None

    mood_trend = [{
        "date": s.started_at.isoformat(),
        "initialMood": s.initial_mood,
        "finalMood": s.final_mood
    } for s in sessions]

    return jsonify({
        "totalSessions": total_sessions,
        "avgInitialMood": avg_initial,
        "avgFinalMood": avg_final,
        "avgImprovement": avg_improvement,
        "moodTrend": mood_trend
    }), 200


# ============================================
# MAIN ROUTE
# ============================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
@limiter.limit("30 per minute; 200 per day")
def chat():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    session_id   = data.get("sessionId")
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Validate session belongs to current user
    therapy_session = None
    if session_id:
        therapy_session = TherapySession.query.filter_by(
            id=session_id, user_id=current_user.id
        ).first()

    # Build intake context from DB
    intake = current_user.intake.data if current_user.intake else {}

    # Fetch last 3 completed session summaries for AI memory
    past_sessions = TherapySession.query.filter(
        TherapySession.user_id == current_user.id,
        TherapySession.completed_at.isnot(None),
        TherapySession.summary.isnot(None)
    ).order_by(TherapySession.started_at.desc()).limit(3).all()

    past_context = ""
    if past_sessions:
        summaries = "\n".join([
            f"- {s.started_at.strftime('%b %d, %Y')}: {s.summary}"
            for s in reversed(past_sessions)
        ])
        past_context = f"\n\nPrevious session notes:\n{summaries}"

    # Build message history from DB for this session
    if therapy_session:
        db_history = ChatMessage.query.filter_by(session_id=session_id)\
            .order_by(ChatMessage.timestamp).all()
        safe_history = [{"role": m.role, "content": m.content} for m in db_history]
    else:
        # Fallback: use history from request body (prompt-injection safe)
        raw_history = data.get("history", [])
        safe_history = [
            {"role": msg["role"], "content": str(msg["content"])}
            for msg in raw_history
            if isinstance(msg, dict) and msg.get("role") in ALLOWED_ROLES
        ]

    messages = [
        {"role": "system", "content": build_system_prompt(intake) + past_context},
        *safe_history,
        {"role": "user", "content": user_message},
    ]

    # Crisis detection (placeholder — to be replaced with dedicated safety AI)
    severity, trigger_phrase = detect_crisis(user_message)
    if severity:
        alert = SafetyAlert(
            user_id=current_user.id,
            session_id=session_id,
            trigger_phrase=trigger_phrase,
            severity_level=severity,
            action_taken="AI provided crisis resources" if severity in ("MEDIUM", "CRITICAL") else "Logged"
        )
        if severity == "CRITICAL" and current_user.guardian:
            alert.notified_at = datetime.utcnow()
        db.session.add(alert)
        db.session.commit()

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        reply = response.choices[0].message.content

        # Store messages in DB
        if therapy_session:
            db.session.add(ChatMessage(session_id=session_id, role="user", content=user_message))
            db.session.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
            db.session.commit()

        return jsonify({"reply": reply, "severityDetected": severity})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=False)
