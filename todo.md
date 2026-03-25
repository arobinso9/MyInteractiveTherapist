# ZenShell — To Do

## Status: Code complete. Ready for testing + deployment.

---

## Next Steps (in order)

### 1. Install new packages locally
```
.venv/Scripts/pip.exe install flask-login flask-bcrypt flask-limiter flask-sqlalchemy
```

### 2. Test locally — full flow
- Create `.env` file in project root with:
  ```
  OPENAI_API_KEY=sk-...
  SECRET_KEY=any-random-string
  FLASK_ENV=development
  ```
- Run the app:
  ```
  .venv/Scripts/python.exe app.py
  ```
- Open http://127.0.0.1:5000 and test every flow:
  - [ ] Sign up
  - [ ] Log in
  - [ ] Complete intake form
  - [ ] Save draft and reload (check banner + restore)
  - [ ] Start a session, send messages
  - [ ] Refresh mid-session (should restore back to chat)
  - [ ] End session, complete post-check
  - [ ] View dashboard (profile summary + session history)
  - [ ] Delete sessions only
  - [ ] Wipe account

### 3. Push to GitHub
```
git add .
git commit -m "Full backend + frontend rewrite with DB"
git push
```

### 4. Deploy to Render
- `render.yaml` is already configured
- On Render dashboard, set these environment variables:
  - `OPENAI_API_KEY`
  - `SECRET_KEY`
  - `FLASK_ENV=production`
  - `DATABASE_URL` (auto-set by Render if you attach a PostgreSQL DB)
