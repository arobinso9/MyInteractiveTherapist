import uuid
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_security import UserMixin, RoleMixin

db = SQLAlchemy()

# ============================================
# ASSOCIATION TABLE
# ============================================
user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id")),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id")),
)


# ============================================
# MODELS
# ============================================
class Role(db.Model, RoleMixin):
    __tablename__ = "roles"
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(30), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=True)
    password      = db.Column(db.String(255), nullable=False)
    active        = db.Column(db.Boolean, default=True)
    fs_uniquifier = db.Column(db.String(64), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    is_pro        = db.Column(db.Boolean, default=False)
    mfa_enabled   = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    roles         = db.relationship("Role", secondary=user_roles, backref=db.backref("users", lazy="dynamic"))

    intake              = db.relationship("IntakeProfile",     backref="user", uselist=False, cascade="all, delete-orphan")
    guardian            = db.relationship("GuardianProfile",   backref="user", uselist=False, cascade="all, delete-orphan")
    sessions            = db.relationship("TherapySession",    backref="user", lazy=True,     cascade="all, delete-orphan")
    assignments         = db.relationship("Assignment",        backref="user", lazy=True,     cascade="all, delete-orphan")
    journal_entries     = db.relationship("JournalEntry",      backref="user", lazy=True,     cascade="all, delete-orphan")
    safety_alerts       = db.relationship("SafetyAlert",       backref="user", lazy=True,     cascade="all, delete-orphan")
    analytics_snapshots = db.relationship("AnalyticsSnapshot", backref="user", lazy=True,     cascade="all, delete-orphan")


class GuardianProfile(db.Model):
    __tablename__ = "guardian_profiles"
    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name              = db.Column(db.String(100))
    email             = db.Column(db.String(120))
    phone             = db.Column(db.String(30), nullable=True)   # E.164 format, e.g. +15551234567
    relationship      = db.Column(db.String(50))
    alert_preferences = db.Column(db.JSON)


class IntakeProfile(db.Model):
    __tablename__ = "intake_profiles"
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    data         = db.Column(db.JSON, nullable=False)
    completed_at = db.Column(db.DateTime)
    updated_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TherapySession(db.Model):
    __tablename__ = "therapy_sessions"
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    started_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at        = db.Column(db.DateTime)
    initial_mood        = db.Column(db.Integer)
    primary_goal        = db.Column(db.Text)
    final_mood          = db.Column(db.Integer)
    what_worked         = db.Column(db.Text)
    feelings_post       = db.Column(db.Text)
    modality_used       = db.Column(db.String(20))
    effectiveness_score = db.Column(db.Float)
    summary             = db.Column(db.Text)
    brief_summary       = db.Column(db.Text)   # 2-3 bullet points for older session context
    embedding           = db.Column(db.Text)

    messages = db.relationship("ChatMessage", backref="session", lazy=True, cascade="all, delete-orphan")
    alerts   = db.relationship("SafetyAlert", backref="session", lazy=True, cascade="all, delete-orphan")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id         = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("therapy_sessions.id"), nullable=False)
    role       = db.Column(db.String(10), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    timestamp  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Assignment(db.Model):
    __tablename__ = "assignments"
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id   = db.Column(db.Integer, db.ForeignKey("therapy_sessions.id", ondelete="SET NULL"))
    title        = db.Column(db.String(100), nullable=False)
    description  = db.Column(db.Text)
    status       = db.Column(db.String(20), default="assigned")
    due_date     = db.Column(db.DateTime)
    feedback     = db.Column(db.Text)
    completed_at = db.Column(db.DateTime)


class JournalEntry(db.Model):
    __tablename__ = "journal_entries"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    image_url  = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class SafetyAlert(db.Model):
    __tablename__ = "safety_alerts"
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id     = db.Column(db.Integer, db.ForeignKey("therapy_sessions.id"))
    trigger_phrase = db.Column(db.Text)
    severity_level = db.Column(db.String(10))
    timestamp      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notified_at    = db.Column(db.DateTime)
    action_taken   = db.Column(db.Text)
    resolved       = db.Column(db.Boolean, default=False)


class AnalyticsSnapshot(db.Model):
    __tablename__ = "analytics_snapshots"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    week_start = db.Column(db.DateTime)
    data       = db.Column(db.JSON)


class EmergencyAlert(db.Model):
    __tablename__ = "emergency_alerts"
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id          = db.Column(db.Integer, db.ForeignKey("therapy_sessions.id"), nullable=True)
    message_id          = db.Column(db.String(64), nullable=True)   # SafetyAlert.id stringified
    idempotency_key     = db.Column(db.String(200), unique=True, nullable=False, index=True)
    # Overall status: DISPATCHING | SENT | PARTIALLY_SENT | FAILED
    status              = db.Column(db.String(20), default="DISPATCHING", nullable=False)
    # Per-channel statuses: PENDING | IN_FLIGHT | DELIVERED | FAILED | SKIPPED
    sms_status          = db.Column(db.String(20), default="PENDING", nullable=False)
    email_status        = db.Column(db.String(20), default="PENDING", nullable=False)
    sms_provider_id     = db.Column(db.String(100), nullable=True)   # Twilio Message SID
    email_provider_id   = db.Column(db.String(100), nullable=True)   # SendGrid X-Message-Id
    sms_attempt_count   = db.Column(db.Integer, default=0, nullable=False)
    email_attempt_count = db.Column(db.Integer, default=0, nullable=False)
    sms_last_error      = db.Column(db.Text, nullable=True)
    email_last_error    = db.Column(db.Text, nullable=True)
    first_triggered_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_attempt_at     = db.Column(db.DateTime, nullable=True)
    completed_at        = db.Column(db.DateTime, nullable=True)
    # Immutable snapshot of user/guardian contact info at alert creation time
    payload_snapshot    = db.Column(db.JSON, nullable=True)

    webhook_events = db.relationship("ProviderWebhookEvent", backref="alert", lazy=True)


class ProviderWebhookEvent(db.Model):
    __tablename__ = "provider_webhook_events"
    id                = db.Column(db.Integer, primary_key=True)
    provider          = db.Column(db.String(20), nullable=False)        # "twilio" | "sendgrid"
    provider_event_id = db.Column(db.String(200), nullable=False)       # unique per provider
    alert_id          = db.Column(db.Integer, db.ForeignKey("emergency_alerts.id"), nullable=True)
    raw_payload       = db.Column(db.JSON, nullable=True)
    received_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("provider", "provider_event_id", name="uq_provider_event"),
    )


class UserRiskState(db.Model):
    __tablename__ = "user_risk_states"
    id                          = db.Column(db.Integer, primary_key=True)
    user_id                     = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    possible_harm_count_24h     = db.Column(db.Integer, default=0)
    possible_harm_count_7d      = db.Column(db.Integer, default=0)
    prior_warning_shown         = db.Column(db.Boolean, default=False)
    last_warning_at             = db.Column(db.DateTime, nullable=True)
    last_risk_level             = db.Column(db.String(30), nullable=True)
    trend                       = db.Column(db.String(10), default="NONE")   # NONE / MILD / MODERATE / SEVERE
    human_review_queued         = db.Column(db.Boolean, default=False)
    emergency_protocol_activated = db.Column(db.Boolean, default=False)
    updated_at                  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("risk_state", uselist=False))
