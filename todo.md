# ZenShell — Dev Notes (2026-04-20)

---

## Emergency Alert System — IN PROGRESS (next session starts here)

### Done:
- `models.py` — `EmergencyAlert` + `ProviderWebhookEvent` models added. `phone` field added to `GuardianProfile`.
- `services/__init__.py` — created
- `services/notifications/__init__.py` — created
- `tests/__init__.py` — created
- `services/emergency_alerts.py` — fully written:
  - `trigger_emergency_alert()` — idempotent, creates alert + dispatches background threads
  - `_channel_with_retry()` — retry loop (delays: 0s, 15s, 1m, 5m, 15m — max 5 attempts)
  - `reconcile_alert_status()` — sets SENT / PARTIALLY_SENT / FAILED / DISPATCHING
  - `RetriableError` / `NonRetriableError` exception classes
  - `_run_in_background()` — daemon thread with app context (TODO: swap for Celery)

### Still TODO (in order):

1. **`services/notifications/twilio_sms.py`**
   - `send_guardian_sms(alert_id)`
   - `handle_twilio_webhook(req)` — verify Twilio signature, idempotent status updates
   - Status map: queued/sent/accepted→IN_FLIGHT, delivered→DELIVERED, failed/undelivered→FAILED
   - Non-retriable codes: 21211, 21214, 21606, 21610, 20003, 20404

2. **`services/notifications/sendgrid_email.py`**
   - `send_guardian_email(alert_id)`
   - `handle_sendgrid_webhook(req)` — verify SendGrid ECDSA signature, batched events
   - Status map: processed/deferred→IN_FLIGHT, delivered→DELIVERED, bounce/dropped/blocked→FAILED

3. **`routes/webhooks.py`**
   - `POST /webhooks/twilio/sms`
   - `POST /webhooks/sendgrid/events`

4. **`app.py`** — register `webhooks_bp`

5. **`utils/risk_engine.py`** — replace `_notify_emergency_contact` stub with real call to `trigger_emergency_alert`

6. **`requirements.txt`** — add `twilio>=9.0.0` and `sendgrid>=6.10.0`

7. **`tests/test_emergency_alerts.py`** — idempotency, retries, duplicate webhooks, reconciliation, failure handling

### Key design decisions:
- Idempotency key format: `emergency:{user_id}:{session_id}:{safety_alert_id}`
- Payload snapshot saved at creation — immutable even if guardian info later changes/deleted
- Both channels (SMS + email) dispatch independently in separate background threads
- `ProviderWebhookEvent` unique constraint on `(provider, provider_event_id)` prevents duplicate webhook processing
- `IN_FLIGHT` is terminal in retry loop — do not resend once queued with provider
- `SKIPPED` = no contact info for that channel. Overall alert only fails if BOTH channels skip.

### Env vars to add to .env + Render dashboard:
```
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=             # E.164 format e.g. +15551234567
TWILIO_CALLBACK_BASE_URL=       # e.g. https://yourapp.onrender.com
SENDGRID_API_KEY=
SENDGRID_FROM_EMAIL=            # verified sender in SendGrid
SENDGRID_WEBHOOK_VERIFICATION_KEY=   # Mail Settings → Event Webhook in SendGrid dashboard
```

---

## Safety Pipeline — COMPLETE

Three-layer AI safety system fully built and hardened:

1. **`utils/risk_triage.py`** — GPT-4.1-mini classifies every incoming user message
2. **`utils/risk_engine.py`** — Deterministic policy engine (Routes A–E), progressive trend, decay
3. **`utils/safety_review.py`** — Outgoing review of every therapist reply before sending
4. **`routes/chat.py`** — Full pipeline wired end to end

---

## Earlier Completed Work
- Flask-Security-Too auth upgrade (replaced Flask-Login + Flask-Bcrypt)
- `app.py` modularized into factory + `config.py` + `extensions.py`
- `app.js` split into ES modules (auth, intake, session, dashboard, account, crisis)
- Session RAG: last 10 full summaries + older brief summaries
- HaveIBeenPwned k-anonymity password breach checking

---

## Deployment checklist (when ready)
- [ ] Add all env vars above to Render dashboard
- [ ] `pip install twilio sendgrid` + update `requirements.txt`
- [ ] Point Twilio status callback URL to `https://yourapp.onrender.com/webhooks/twilio/sms`
- [ ] Point SendGrid Event Webhook to `https://yourapp.onrender.com/webhooks/sendgrid/events`
- [ ] Enable SendGrid signed webhooks and copy verification key to env
