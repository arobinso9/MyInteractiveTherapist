import os
from flask import Flask, render_template
from flask_security import Security, SQLAlchemyUserDatastore
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__)

    # Config
    from config import Config
    app.config.from_object(Config)

    # Extensions
    from models import db, User, Role
    db.init_app(app)

    from extensions import limiter
    limiter.init_app(app)

    # Flask-Security
    import extensions
    extensions.user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    extensions.security = Security(app, extensions.user_datastore)

    # OpenAI client — stored on app.extensions for access in blueprints
    _api_key = os.getenv("OPENAI_API_KEY")
    if not _api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    app.extensions["openai_client"] = OpenAI(api_key=_api_key, timeout=30.0, max_retries=1)

    # Create DB tables
    with app.app_context():
        db.create_all()

    # Blueprints
    from routes.auth import auth_bp
    from routes.intake import intake_bp
    from routes.sessions import sessions_bp
    from routes.chat import chat_bp

    for bp in (auth_bp, intake_bp, sessions_bp, chat_bp):
        app.register_blueprint(bp)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=False, threaded=True)
