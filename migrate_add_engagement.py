from app import create_app
from models import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    db.session.execute(text(
        "ALTER TABLE therapy_sessions ADD COLUMN IF NOT EXISTS prior_goal_engagement VARCHAR(20)"
    ))
    db.session.execute(text(
        "ALTER TABLE therapy_sessions ADD COLUMN IF NOT EXISTS pattern_raised BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    db.session.commit()
    print("OK: prior_goal_engagement and pattern_raised columns ensured")
