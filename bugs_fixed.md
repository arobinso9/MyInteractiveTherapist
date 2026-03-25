# Bugs Fixed — Review Pass (2026-03-24)

These are bugs found AFTER the initial Phase 1/2 build — caught during dedicated review sweeps.
All are fixed as of 2026-03-24.

---

## Backend Bugs (app.py)

**Bug 1 — Missing cascade deletes**
- All `User` relationships were missing `cascade="all, delete-orphan"`
- `TherapySession.messages` and `TherapySession.alerts` also missing cascade
- Fix: added `cascade="all, delete-orphan"` to every relationship on `User` and `TherapySession`

**Bug 2 — Deprecated `load_user` API**
- `User.query.get(int(user_id))` is deprecated in SQLAlchemy 2.x
- Fix: changed to `db.session.get(User, int(user_id))`

**Bug 3 — No session cookie security**
- Flask session cookies had no security flags set
- Fix: added `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`, `SESSION_COOKIE_SECURE` set to `True` unless `FLASK_ENV=development`

**Bug 4 — `get_reports` avg calculation wrong**
- Mood values of `0` would be falsy — skipped in avg calculation
- Fix: changed truthiness check to `is not None`

**Bug 5 — JSON column mutation not tracked**
- Updating `current_user.intake.data` (a JSON column) wouldn't be detected by SQLAlchemy
- Fix: added `flag_modified(current_user.intake, "data")` after every mutation

**Bug 6 — `delete_all_sessions` used bulk delete**
- SQLAlchemy bulk `.delete()` bypasses ORM-level cascade — child records (ChatMessage, SafetyAlert) would be orphaned
- Fix: replaced with ORM loop (`for s in sessions: db.session.delete(s)`)

**Bug 7 — `Assignment.session_id` FK had no ondelete rule**
- Deleting a session would fail or leave dangling FK on assignments
- Fix: added `ondelete="SET NULL"` to the FK definition

**Bug 8 — `/api/login` missing `isPro` in response**
- Frontend `handleLogin()` sets `currentUser.isPro` from the response, but the field wasn't returned
- Fix: added `"isPro": user.is_pro` to the login response JSON

**Bug 9 — Missing import**
- `flag_modified` was used but not imported
- Fix: added `from sqlalchemy.orm.attributes import flag_modified`

---

## Frontend Bugs (app.js)

**Bug 1 — `hideLockoutMessage()` called but function was renamed**
- Function was renamed to `hideAuthError()` but old name still called on line 407
- Fix: updated call to `hideAuthError()`

**Bug 2 — Syntax error in `sendMessage()`**
- `'I'm having trouble...'` — straight apostrophe inside single-quoted string = syntax error
- Fix: changed to double quotes `"I'm having trouble..."`

**Bug 3 — `sessionStorage` not cleared in delete/logout flows**
- `activeSessionId` would persist in sessionStorage after logout, wipe, or delete — stale session could be restored on next login
- Fix: added `sessionStorage.removeItem('activeSessionId')` to `logout()`, `completeSession()`, `deleteSessionsOnly()`, `wipeAccount()`, `startNewSession()`

**Bug 4 — `wipeAccount()` used raw localStorage**
- Still calling old localStorage-based `safeSaveUser` / raw writes
- Fix: replaced with `DELETE /api/account` fetch call

**Bug 5 — `deleteSessionsOnly()` used `safeSaveUser`**
- Same issue — old localStorage code still in place
- Fix: replaced with `DELETE /api/sessions` fetch call

**Bug 6 — `callChatAPI()` sent stale `intake` from `currentUser.intakeData`**
- `currentUser.intakeData` no longer exists (localStorage removed); backend now reads intake from DB via sessionId
- Fix: removed `intake` from request body; added `sessionId: tempSessionData.sessionId || null`

**Bug 7 — `renderProfileSummary()` read `currentUser.intakeData`**
- Field no longer exists on `currentUser`
- Fix: made async, now fetches `GET /api/intake`

**Bug 8 — `renderSessionHistory()` read `currentUser.sessions`**
- Field no longer exists on `currentUser`
- Fix: made async, now fetches `GET /api/sessions`

**Bug 9 — `completeSession()` called `safeSaveUser`**
- Old localStorage function, no longer exists
- Fix: replaced with `POST /api/sessions/<id>/complete`

**Bug 10 — `enterTherapySession()` read `currentUser.intakeData`**
- Field no longer exists; also wasn't creating a session in DB
- Fix: made async, now POSTs to `/api/sessions` to get `sessionId`, stores in `tempSessionData` and `sessionStorage`

**Bug 11 — Session restore on refresh routed to wrong view**
- After restoring an active session from `sessionStorage` into `tempSessionData`, the app still called `render('progress')` — user landed on dashboard instead of back in the chat
- Fix: added `renderChatMessages()` + `render('session')` + early `return` when active session is restored
