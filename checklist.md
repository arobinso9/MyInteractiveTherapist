# ZenShell — Build Checklist

## Status: Phase 1 and Phase 2 both COMPLETE as of 2026-03-24.

---

## Phase 1 — Backend (app.py) ✅ All done

| # | Task | Status |
|---|------|--------|
| 1 | Clean up old/extra files | ✅ |
| 2 | Rate limiting on `/api/chat` | ✅ |
| 3 | DB schema (9 tables) | ✅ |
| 4 | Auth endpoints (`/api/signup`, `/api/login`, `/api/logout`, `/api/me`) | ✅ |
| 5 | Intake endpoints (GET/POST `/api/intake`) | ✅ |
| 6 | Session endpoints (GET/POST `/api/sessions`, complete, get by id) | ✅ |
| 7 | Journal, safety, reports endpoints | ✅ |
| 8 | `render.yaml` with PostgreSQL | ✅ |
| 9 | `requirements.txt` updated | ✅ |
| 10 | `postgres://` → `postgresql://` fix | ✅ |

**Additional backend bugs caught and fixed in review:**
- `cascade="all, delete-orphan"` added to ALL User relationships and TherapySession.messages/alerts
- `load_user` updated from deprecated `User.query.get()` → `db.session.get(User, int(user_id))`
- Session cookie security: `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE="Lax"`, `SESSION_COOKIE_SECURE` (env-aware)
- `get_reports` avg calculation fixed: `is not None` instead of truthiness
- `flag_modified(current_user.intake, "data")` added after JSON column mutation
- `DELETE /api/sessions` added using ORM loop (not bulk — bulk bypasses cascade)
- `DELETE /api/account` endpoint added
- `Assignment.session_id` FK given `ondelete="SET NULL"`
- `/api/login` response now includes `isPro`
- `from sqlalchemy.orm.attributes import flag_modified` import added

---

## Phase 2 — Frontend (app.js rewrite) ✅ All done

| # | Task | Status |
|---|------|--------|
| 10a | `handleLogin()` → `POST /api/login`, stores full `currentUser` | ✅ |
| 10b | `handleSignup()` → `POST /api/signup`, `showAuthSuccess()` | ✅ |
| 10c | `logout()` → async `POST /api/logout` | ✅ |
| 10d | `window.load` → `GET /api/me` + hide loading overlay | ✅ |
| 11a | `loadIntakeForm()` → `GET /api/intake` + loading banner | ✅ |
| 11b | `completeIntake()` → `POST /api/intake` (completed: true) | ✅ |
| 11c | `saveDraft()` → `POST /api/intake` (completed: false) | ✅ |
| 12a | `enterTherapySession()` → `POST /api/sessions` to get `sessionId` | ✅ |
| 12b | `callChatAPI()` → pass `sessionId`, remove stale `intake` from body | ✅ |
| 12c | `completeSession()` → `POST /api/sessions/<id>/complete` | ✅ |
| 12d | `deleteSessionsOnly()` → `DELETE /api/sessions` | ✅ |
| 13a | `renderProfileSummary()` → pull intake from `GET /api/intake` | ✅ |
| 13b | `renderSessionHistory()` → pull sessions from `GET /api/sessions` | ✅ |

**Additional frontend bugs caught and fixed in review:**
- `hideLockoutMessage()` → renamed to `hideAuthError()`
- Straight apostrophe syntax error in `sendMessage()` error text
- `sessionStorage.removeItem('activeSessionId')` added to `logout()`, `completeSession()`, `deleteSessionsOnly()`, `wipeAccount()`, `startNewSession()`
- `wipeAccount()` replaced raw localStorage with `DELETE /api/account`
- Session restore on page refresh: `sessionStorage` persists `activeSessionId`; on load fetches and restores `chatHistory` from DB
- Session restore routing bug: restored session now calls `render('session')` + `renderChatMessages()` instead of going to 'progress'
- `intakeLoadingBanner` added to HTML, CSS, and `loadIntakeForm()`

---

## Next Steps (in order)

1. **Install new packages locally**
   ```
   .venv/Scripts/pip.exe install flask-login flask-bcrypt flask-limiter flask-sqlalchemy
   ```

2. **Test locally**
   - Create `.env` with `OPENAI_API_KEY=sk-...`
   - Run: `.venv/Scripts/python.exe app.py`
   - Test full flow: signup → intake → session → complete → dashboard → delete

3. **Push to GitHub**

4. **Deploy to Render**
   - `render.yaml` is already configured
   - Set env vars on Render dashboard: `OPENAI_API_KEY`, `FLASK_ENV=production`, `SECRET_KEY`, `DATABASE_URL`
