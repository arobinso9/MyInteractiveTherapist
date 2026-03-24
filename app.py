import os
from flask import Flask, render_template, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
@limiter.limit("30 per minute; 200 per day")
def chat():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    intake = data.get("intake", {})
    history = data.get("history", [])
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Only allow user/assistant roles in history — prevent prompt injection
    safe_history = [
        {"role": msg["role"], "content": str(msg["content"])}
        for msg in history
        if isinstance(msg, dict) and msg.get("role") in ALLOWED_ROLES
    ]

    messages = [
        {"role": "system", "content": build_system_prompt(intake)},
        *safe_history,
        {"role": "user", "content": user_message},
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=False)
