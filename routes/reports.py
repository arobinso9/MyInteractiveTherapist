from flask import Blueprint, jsonify
from flask_security import auth_required, current_user
from models import TherapySession

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/api/reports", methods=["GET"])
@auth_required()
def get_reports():
    sessions = TherapySession.query.filter(
        TherapySession.user_id == current_user.id,
        TherapySession.completed_at.isnot(None)
    ).order_by(TherapySession.started_at).all()

    total_sessions  = len(sessions)
    initial_moods   = [s.initial_mood for s in sessions if s.initial_mood is not None]
    final_moods     = [s.final_mood   for s in sessions if s.final_mood   is not None]
    avg_initial     = round(sum(initial_moods) / len(initial_moods), 1) if initial_moods else None
    avg_final       = round(sum(final_moods)   / len(final_moods),   1) if final_moods   else None
    avg_improvement = round(avg_initial - avg_final, 1) if avg_initial is not None and avg_final is not None else None

    mood_trend = [{
        "date":        s.started_at.isoformat(),
        "initialMood": s.initial_mood,
        "finalMood":   s.final_mood
    } for s in sessions]

    return jsonify({
        "totalSessions":  total_sessions,
        "avgInitialMood": avg_initial,
        "avgFinalMood":   avg_final,
        "avgImprovement": avg_improvement,
        "moodTrend":      mood_trend
    }), 200
