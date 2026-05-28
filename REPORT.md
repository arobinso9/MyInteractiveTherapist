# ZenShell — An AI-Driven Psychotherapy Platform
### Final Project Report

**Author:** Aviva Robinson
**TID:** T00521651
**Project repository:** `MyInteractiveTherapist` (working name: *Zen Therapy* → *ZenShell*)
**Reporting period:** February – May 2026
**Codebase at submission:** ~4,850 lines across Python (Flask backend) and vanilla-JS ES modules (frontend)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Application: What ZenShell Is](#2-the-application-what-zenshell-is)
3. [Feature Catalog](#3-feature-catalog)
4. [System Architecture](#4-system-architecture)
5. [The AI Safety Pipeline (Technical Centerpiece)](#5-the-ai-safety-pipeline-technical-centerpiece)
6. [Data Model](#6-data-model)
7. [Security & Privacy Engineering](#7-security--privacy-engineering)
8. [How I Used AI to Develop ZenShell](#8-how-i-used-ai-to-develop-zenshell)
9. [Validation & Quality Control](#9-validation--quality-control)
10. [The Development Journey: Pivots, Setbacks, and Removed Work](#10-the-development-journey-pivots-setbacks-and-removed-work)
11. [Engineering Challenges & How I Solved Them](#11-engineering-challenges--how-i-solved-them)
12. [Skills Acquired](#12-skills-acquired)
13. [Current State & Future Work](#13-current-state--future-work)
14. [Appendix A: API Endpoint Registry](#appendix-a-api-endpoint-registry)
15. [Appendix B: Database Schema](#appendix-b-database-schema)
16. [Appendix C: Commit Timeline](#appendix-c-commit-timeline)

---

## 1. Executive Summary

**ZenShell** is a web-based AI psychotherapy platform. A user creates a secure account, fills out a clinical 12-section intake form, and then holds conversational therapy "sessions" with an AI therapist. Around that conversation sits the part of the project I consider the real engineering achievement: a **multi-stage AI safety pipeline** that screens every incoming user message for risk, runs a deterministic policy engine that decides how to respond, reviews every outgoing AI reply for harmful content, and fires a crisis-resource modal when someone is in danger. The platform also remembers prior sessions (a form of retrieval-augmented memory), helps the user set and follow up on between-session goals, and tracks mood over time.

The project evolved through several complete architectural rewrites. It began as a single-file HTML/JS prototype storing data in the browser's `localStorage`, and ended as a modular Flask application backed by a Neon PostgreSQL database, a token-authenticated REST API, and an ES-module frontend. Along the way I built and then deliberately **removed** entire subsystems — a Twilio/SendGrid guardian-notification system, multiple deployment configurations, and several speculative database tables — because testing and reflection showed they were the wrong fit for the product. Those removals are documented here as evidence of iterative judgment, not omitted.

Critically: **I was permitted to use AI, and I used it heavily and deliberately.** This report is explicit about exactly how. AI played two distinct roles in this project — it is both the *core technology of the product* (four OpenAI GPT-4.1 model calls power the therapist, the risk triage, the safety review, and the session summaries) and the *primary tool I used to build the product* (I worked with a multi-model workflow — Gemini, ChatGPT, and Claude Code — to design, generate, audit, and refactor the code). What follows separates what the AI did from what I did, and shows where my own judgment, testing, and design decisions were essential and irreplaceable.

---

## 2. The Application: What ZenShell Is

ZenShell is a single-page application (SPA) served by a Flask backend. The user-facing experience flows through six views, controlled by a client-side router (`static/js/main.js`, `render(route)`):

1. **Auth** — sign up / log in, with live password-strength feedback.
2. **Intake** — a 12-section clinical questionnaire (the AI's "knowledge base" about the client).
3. **Progress / Dashboard** — profile summary, session history, mood trends.
4. **Pre-check** — entry slip: a mood rating plus (if applicable) a check-in on the goal set last session.
5. **Session** — the live AI therapy chat.
6. **Post-check** — exit slip: final mood rating, key takeaway, and the goal carried forward.

The application is designed to feel like a continuous therapeutic relationship rather than a stateless chatbot. The AI greets returning clients by name, remembers what was discussed in previous sessions, holds onto safety-relevant threads across conversation turns, and follows up on commitments the client made. It also enforces clinical guardrails: it never diagnoses or prescribes, it escalates to crisis resources only when there is genuine immediate danger, and every reply it produces is independently screened before the user ever sees it.

**Design language:** a calm "Zen" aesthetic — a sage/sand color palette, Inter and Playfair Display typography, and a clean, professional clinical feel (`static/style.css`, ~1,340 lines).

> **Scope note:** ZenShell currently runs **locally** (`python app.py`) against a hosted Neon PostgreSQL database. It is a functional, end-to-end working application, not a deployed public service — a deliberate decision explained in §10.

---

## 3. Feature Catalog

The following features are present in the **final, submitted codebase** and have been verified against the source.

### 3.1 Authentication & Account Management
- **Account creation** with server-side validation (`routes/auth.py`): username rules (3–30 chars, alphanumeric + underscore), uniqueness enforcement.
- **Token-based authentication** via **Flask-Security-Too**, replacing an earlier Flask-Login/Bcrypt setup. Passwords are hashed with bcrypt; protected endpoints use the `@auth_required()` decorator.
- **Session persistence & restoration** — on page refresh, an in-progress therapy session is reconstructed from the database (`main.js` reads `sessionStorage` → `GET /api/sessions/<id>`), so therapeutic progress is never lost to an accidental reload.
- **Two-tier account deletion** ("the right to disappear"):
  - *Delete sessions* — a modal lets the user pick specific sessions to delete (checkbox list of the 10 most recent) or wipe all of them, while keeping the account and intake intact (`account.js`).
  - *Wipe account* — a two-step confirmation that deletes the user and everything cascaded from it. SQLAlchemy `cascade="all, delete-orphan"` ensures no orphaned clinical data remains; `UserRiskState` is manually deleted first to avoid a foreign-key violation (`routes/auth.py`).

### 3.2 Password Security (Client-Side, Privacy-Preserving)
- **Live strength meter** — checks length (≥10), upper/lower case, number, special character, with a color-coded bar and a real-time requirements checklist (`auth.js`).
- **Common-pattern rejection** — a regex blocklist catches `password`, `qwerty`, `123456`, all-letters, repeated characters, etc.
- **Breach checking via HaveIBeenPwned k-anonymity** — the password is SHA-1 hashed in the browser; only the **first 5 hash characters** are sent to the HIBP range API, with `Add-Padding` enabled to defeat traffic analysis. The password itself never leaves the device. If the suffix matches a known breach, signup is blocked with the breach count shown; if HIBP is unreachable, the check fails open (warns but doesn't block).
- **Username-in-password rejection** — prevents trivially guessable passwords.

### 3.3 Clinical Intake Form (12 Sections)
A comprehensive questionnaire (`templates/index.html`, collected and validated in `intake.js`) covering: basic information, presenting concerns, **risk assessment** (suicidal ideation, prior attempts, self-harm, harm-to-others, current-safety), mental-health history, medical/medication history, substance use, trauma screening, relationships, daily functioning, therapy/therapist-style preferences, cultural factors, and top-three goals. Highlights:
- **Field-level validation** with specific error messages, minimum word/length counts, and conditional requirements (e.g., "when" is required if prior attempts = yes).
- **Draft saving** — partial intake can be saved (`completed: false`) and resumed later.
- **Immediate crisis interception** — if the user reports they are *not currently safe* or have an *active plan*, the form blocks submission and surfaces 988/911 before anything else.
- Stored as a **flexible JSON column** (`intake_profiles.data`), which let the schema evolve without migrations.

### 3.4 The AI Therapist
- Powered by **OpenAI GPT-4.1** (`routes/chat.py`), driven by a server-side system prompt (`utils/prompts.py`, `build_system_prompt`).
- **Persona & clinical guardrails:** warm, empathetic, evidence-based (CBT/DBT/motivational interviewing); asks one focused question at a time; never diagnoses or prescribes; uses the client's name *sparingly* (a tuned behavior — see §8).
- **AI-generated opening greeting** (`/api/sessions/<id>/greeting`, GPT-4.1-mini) — greets the returning client by preferred name and, if a goal was set last time, invites them to discuss it or move on. A fast hardcoded greeting is used when there's nothing substantive to reference (no wasted API call).
- **Sourcing discipline:** the prompt enforces a strict recency hierarchy (current session > recent sessions > older sessions > intake) and bans "document language" ("your intake form," "your file") and false time-claims, so the AI sounds like it *remembers* rather than *reads a chart*.

### 3.5 Cross-Session Memory (Retrieval-Augmented Generation)
- On each turn, the chat route loads the user's prior completed sessions and injects them into the system prompt as `past_context` (`routes/chat.py`).
- **Dual-summary scheme:** the **10 most recent** sessions are injected as full summaries; **older** sessions as 2–3 sentence briefs. Summaries are generated at session completion by GPT-4.1-mini and split via a `---BRIEF---` delimiter into a full and brief version (`routes/sessions.py`).
- **Scope-restricted summaries:** summaries capture only what *the client* brought up — the prompt explicitly excludes the therapist's own memory-cue callbacks to prevent the AI's prompts from polluting the record (the most recent commit, `6b0501c`).

### 3.6 Goal-Setting & Follow-Through Loop
A multi-step feature spanning schema, endpoints, prompts, and frontend:
- **Wrap-up** (`/api/sessions/<id>/wrap-up`, GPT-4.1): when the user ends a substantive session, the therapist proposes one small, specific, actionable goal (≤50 words) in a warm closing message.
- **Refinement in chat:** a `wrapUp: true` flag lets the user push back on or refine the proposed goal conversationally before committing.
- **Pre-check check-in:** at the *start* of the next session, if the prior session set a goal, the entry screen shows it with **structured radio buttons** (yes / partial / no) and a **required** explanation note (`session.js`).
- The radio answer + note + prior goal all surface into the AI's first-turn context with instructions to engage specifically with what the client wrote.
- **Trivial-session safety net:** sessions with ≤5 user messages skip goal-setting and get a tight 1–2 sentence summary instead of the full treatment.

### 3.7 Crisis Detection & Response
- The safety pipeline (§5) classifies risk and, on confirmed immediate danger, **blocks normal therapy** and returns a hardcoded crisis response (988, 741741, 911).
- The frontend pops a **styled crisis modal** with hotline resources whenever the API returns `safetyMode: CRISIS` (`crisis.js`).
- **Crisis response is user-facing only** — there are no SMS/email/guardian notifications (this was built and then deliberately removed; see §10).

### 3.8 Mood Tracking & Dashboard
- Entry and exit mood ratings (1–10 stress scale) per session.
- Session history cards show initial vs. final mood with human-readable deltas ("↓ Felt better (stress -3)" / "↑ Felt worse" / "→ No change") — corrected from an earlier ambiguous label (§10).
- Profile summary derived live from intake.

### 3.9 UX Infrastructure
- **Reusable promise-based modal system** (`modal.js`) — `showModal` / `confirmModal` / `alertModal` return Promises so calling code can `await` a user's choice. This replaced inconsistent native `confirm()`/`alert()` dialogs.
- **Loading/"Thinking…" states** throughout, so the UI is never silently blocked on an API call.
- **Timezone correctness** — all serialized timestamps append `"Z"` so the browser converts UTC → local time correctly (§11).
- **Cache-busting for development** — `SEND_FILE_MAX_AGE_DEFAULT = 0` forces fresh static files on every load.

---

## 4. System Architecture

### 4.1 Stack
| Layer | Technology |
|---|---|
| Web framework | Flask 3.1 (application-factory pattern) |
| Auth | Flask-Security-Too 5.8 (token authentication) |
| ORM / DB | Flask-SQLAlchemy 3.1 / SQLAlchemy 2.0 → **Neon PostgreSQL** |
| Rate limiting | Flask-Limiter 4.1 (in-memory store) |
| AI | OpenAI Python SDK 2.x — GPT-4.1 and GPT-4.1-mini |
| Secrets | python-dotenv (`.env`, never hardcoded) |
| Frontend | Vanilla JavaScript **ES modules** (no framework), HTML, CSS |

### 4.2 Backend layout (modular)
```
app.py            # application factory: config, extensions, blueprints, OpenAI client
config.py         # Config class: DB URL normalization, cookie security, cache control
extensions.py     # limiter, user_datastore, security singletons
models.py         # SQLAlchemy models (7 tables + association)
routes/
  auth.py         # signup, login, logout, me, delete account
  intake.py       # get / save intake
  sessions.py     # create, list, get, delete, greeting, wrap-up, complete
  chat.py         # the orchestrator: triage → policy → generate → review → persist
utils/
  prompts.py      # build_system_prompt, build_greeting_prompt
  risk_triage.py  # GPT-4.1-mini incoming risk classifier + parser
  risk_engine.py  # deterministic policy engine + stateful trend tracking
  safety_review.py# GPT-4.1-mini outgoing reply reviewer + parser
```

### 4.3 Key architectural decisions
- **Application-factory pattern** (`create_app()`) — clean separation of config, extensions, and blueprints; the OpenAI client is created once and stored on `app.extensions` for reuse.
- **Fail-fast on misconfiguration** — the app raises `RuntimeError` at startup if `OPENAI_API_KEY` is missing.
- **Postgres URL normalization** — auto-rewrites `postgres://` → `postgresql://` (a portability fix carried over from the hosted-deployment era).
- **Server-authoritative chat history** — the `/api/chat` endpoint reads conversation history from the database keyed by `sessionId` and **ignores any history sent by the client**, which prevents prompt-injection / history-rewriting attacks (only used as a fallback for unsaved sessions).

---

## 5. The AI Safety Pipeline (Technical Centerpiece)

This is the most sophisticated part of the system and the piece I'm proudest of. Every chat turn passes through a deterministic, multi-stage pipeline in `routes/chat.py`. The design principle: **AI models classify and generate, but a hard-coded policy engine — not a model — decides what happens.** Models can be wrong; the control flow around them is deterministic and fails safe.

### Stage 1 — Incoming Risk Triage (`utils/risk_triage.py`, GPT-4.1-mini)
Classifies the user's message into one of three levels:
- `NO_RISK` (the default — ordinary venting, sadness, frustration are explicitly *not* risk),
- `POSSIBLE_HARM` (passive ideation, self-harm urges, ambiguous violent thoughts),
- `CLEAR_IMMEDIATE_RISK` (a direct statement of intent, *or* concerning content paired with plan/means/timing/inability to stay safe).

The prompt includes a **hyperbole filter** ("this meeting is killing me" ≠ risk) and a hardcoded list of direct statements ("I want to kill myself") that escalate to `CLEAR_IMMEDIATE_RISK` *on their own with no modifier required* — a fix I identified through testing (§11). Output is parsed into a structured dict; the model **fails safe to `POSSIBLE_HARM`** on any error or malformed output, and the chat route validates every field before trusting it.

### Stage 2 — Deterministic Policy Engine (`utils/risk_engine.py`)
A non-AI state machine that consumes the triage verdict and returns a `safety_mode` of `NORMAL`, `HEIGHTENED`, or `CRISIS`. It includes:
- A **`NO_RISK` short-circuit** — no alert, no warning, normal therapy (this fix eliminated the bug where every "hi" was treated as possible harm; §11).
- **Stateful trend tracking** via the `UserRiskState` table — a trend that advances (`NONE → MILD → MODERATE → SEVERE`) only on *meaningful* signals (high/medium confidence, or specific escalation keywords like "tonight," "pills," "plan") and **decays** on low-confidence noise.
- **Warning throttling** (one warning per 10-minute window) and a human-review-queue flag for escalating patterns.
- **Idempotent crisis routing** — `CLEAR_IMMEDIATE_RISK` or an emergency action immediately returns `block_therapy: True` with a **hardcoded** crisis response (never model-generated, so it can't be jailbroken).

### Stage 3 — Therapist Generation + Outgoing Review Loop (`utils/safety_review.py`, GPT-4.1-mini)
The GPT-4.1 therapist produces a draft. Before it reaches the user, a separate GPT-4.1-mini reviewer screens it. The reviewer is intentionally **permissive** — its job is narrow: catch only genuinely harmful advice (encouraging self-harm, giving a diagnosis as fact, telling someone to change meds) or replies that *ignore* a serious disclosure. It returns `APPROVE` / `REVISE` / `BLOCK`:
- `APPROVE` → the **original draft** is sent (a key fix — see the "AI has no memory" bug in §11).
- `REVISE` → a minimally edited safe version is sent.
- `BLOCK` → the draft is discarded and the loop retries with feedback, up to 3 times, falling back to a safe message.

The reviewer **fails open** (approves the original) on error, so a reviewer outage never breaks the chat.

### Stage 4 — Hotline Sync Backstop (`routes/chat.py`)
A defense-in-depth layer I added after a design debate (§8, §11): if the *therapist's reply itself* contains hotline keywords (988, 741741, "crisis text line," etc.) but triage didn't already flag crisis, the backend **upgrades `safetyMode` to `CRISIS`** so the modal still fires, and logs a `HOTLINE_SYNC` warning. This means the two safety systems can never silently disagree — if either one thinks it's a crisis, the user gets the resources.

**Why this matters:** the pipeline is layered so that no single model failure can let a dangerous reply through or suppress a needed crisis response. Triage can misfire, the reviewer can misfire, the therapist can misfire — but the deterministic engine and the keyword backstop catch the gaps.

---

## 6. Data Model

The final schema is **7 tables plus a `user_roles` association table** (`models.py`). *(An earlier iteration had 9 tables including `guardian_profiles`, `assignments`, `journal_entries`, and `analytics_snapshots`; these were trimmed when the corresponding features were cut or deferred — see §10.)*

| Table | Purpose |
|---|---|
| `roles` / `user_roles` | Flask-Security role plumbing |
| `users` | account, bcrypt password, `fs_uniquifier` token, `is_pro` flag |
| `intake_profiles` | full clinical intake as a JSON column |
| `therapy_sessions` | per-session metadata: moods, summary, brief_summary, next_session_goal, prior_goal_followthrough, prior_goal_note |
| `chat_messages` | every message, with role + content + timestamp |
| `safety_alerts` | crisis/risk audit log with severity |
| `user_risk_states` | stateful per-user risk trend, counters, warning/throttle state |

`cascade="all, delete-orphan"` is set on all user-owned relationships so account deletion is clean and complete.

---

## 7. Security & Privacy Engineering

Because this is a mental-health application handling extremely sensitive data, security was a first-class concern throughout:

- **Secrets management** — API keys and DB URLs in `.env`, loaded via python-dotenv; the app refuses to start without the OpenAI key.
- **Password hashing** — bcrypt via Flask-Security-Too.
- **Breach-resistant signup** — HaveIBeenPwned k-anonymity check (the password never leaves the browser).
- **Token auth + cookie hardening** — `SESSION_COOKIE_HTTPONLY`, `SAMESITE=Lax`, and `SECURE` (environment-aware).
- **Prompt-injection defense** — the system prompt is built entirely server-side and is never exposed to or accepted from the client; chat history is read from the DB, not the request body.
- **Rate limiting** — `/api/chat` is capped at 30/min and 200/day to prevent abuse of the costly AI endpoint.
- **XSS prevention** — session text rendered into modal labels is HTML-escaped (`account.js`, `_esc`).
- **User data isolation** — every query is filtered by `user_id`; one user can never read or delete another's data.
- **Auditability** — crisis triggers, hotline syncs, and safety-review blocks are logged with structured context.
- **Right to disappear** — granular session deletion and full-account wipe, with cascade guarantees.

---

## 8. How I Used AI to Develop ZenShell

I was permitted to use AI on this project, and I used it as a central tool — but deliberately, with a clear division of labor and constant verification. AI played **two distinct roles**, and it's worth separating them.

### 8.1 AI as the Product's Core Technology
The application *is* an AI system. Four distinct OpenAI model calls power its behavior:

| Purpose | Model | Where |
|---|---|---|
| The therapist | GPT-4.1 | `routes/chat.py` |
| Incoming risk triage | GPT-4.1-mini | `utils/risk_triage.py` |
| Outgoing reply review | GPT-4.1-mini | `utils/safety_review.py` |
| Session summaries, goal wrap-up, greetings | GPT-4.1 / GPT-4.1-mini | `routes/sessions.py` |

The bulk of my *product* effort went into **prompt engineering** — the system prompt is, as I wrote in an early report, "the entire brain behind the app." I developed it through iterative stress-testing (§9), tuning behaviors like crisis brevity, sourcing discipline, name usage, safety continuity, and the "nudge" toward progress rather than endless validation.

### 8.2 AI as My Development Tool — A Multi-Model Workflow
I did not use a single AI assistant. I built a deliberate **multi-model pipeline** that played each model to its strengths — what I came to call "cross-model polishing" or "triangulation":

- **Gemini — Prompt Engineer & Auditor.** I used Gemini to refine my raw ideas into concise, high-quality prompts to feed other models, and later as a **security/logic auditor** of generated code. Its ability to view screenshots also made it my troubleshooting partner during deployment work when other tools couldn't.
- **ChatGPT (GPT-4o/4.1/5) — Content Generation & Verification.** Drafted the initial structure of the 12-section intake form, elaborated system-prompt language, and served as an independent second opinion that I cross-checked Claude's code against.
- **Claude Code — Lead Developer.** The primary code generator and architect: it wrote the Flask framework, the SQLAlchemy models, the safety pipeline, the ES-module frontend, and executed the multi-file refactors.

The recurring pattern was a **feedback loop**: generate a prompt (Gemini/ChatGPT) → generate code (Claude Code) → audit the code (Gemini/ChatGPT) → inject the audit findings back into Claude Code to refactor. This loop is directly responsible for catching real bugs (§9.4).

The four subsections that follow address, in depth and in order, the specific reflection questions at the heart of this course: **(8.3)** if and how I used prompt engineering, **(8.4)** how I verified the correctness of what the AI produced, **(8.5)** what AI did that I genuinely could not have done versus what merely saved me time, and **(8.6)** what I relied on AI for entirely and the new skills it taught me. **(8.7)** then covers the limits I ran into — where AI could not substitute for my own judgment. Throughout, I name the specific tool I used (Gemini, ChatGPT, Claude Code, or the OpenAI Playground) rather than referring to "AI" generically, because which tool I reached for, and why, was itself a deliberate choice.

### 8.3 If and How I Used Prompt Engineering
Prompt engineering was not incidental to this project — it was, in a real sense, the project. The therapist's system prompt is the "brain" of the app, and I spent dedicated multi-hour sessions on it alone, because I believed (and still do) that the stronger the prompt, the better the app. I used several distinct techniques, deliberately and repeatedly:

- **Persona prompting.** For *development*, I assigned **Claude Code** roles like "Expert Full-Stack Developer," "Lead Architect," and "master prompt engineer," and observed that even a basic functional request produced cleaner, more professional code when prefaced with the right persona. For the *product*, I used **ChatGPT** and **Gemini** to help craft a "Therapist" persona that is empathetic, trauma-informed, and steady, and a "Clinical Psychologist" framing to make the intake questions scientifically sound.
- **Chain-of-Thought (CoT).** I forced **Claude Code** to reason through logic and produce a checklist *before* writing any code — for example, walking through "user isolation" (keeping User A's data away from User B) before it generated the storage logic, and breaking the deterministic Route A–E safety logic into explicit steps. This made its output far more reliable and gave me something concrete to review against.
- **Few-shot prompting.** In the **OpenAI Playground**, I gave the therapist model concrete examples of ideal therapeutic dialogue so it learned the *rhythm* of therapy, not just the topic — the difference between a generic advice-giver and something that feels like a session.
- **Cross-model "triangulation."** This is the technique I'm most proud of developing. When one model plateaued, I moved the work to another: **Gemini** generated strong base prompts but would get "stumped" and stop improving; feeding its output into **ChatGPT (GPT-4o/GPT-5)** produced a jump in nuance and therapeutic depth; sending the result *back* to **Gemini** gave me a safety/psychological-soundness second opinion. I learned that different model architectures have different strengths — **Gemini** was the better safety validator, **ChatGPT** the better elaborator — and I exploited that rather than trusting any single model.
- **Iterative refinement against real failures.** My prompts were never one-shot. The transparency/sourcing rule (which **Claude Code** implemented in `utils/prompts.py`) took several passes: my first version only made the therapist cite its sources when *directly asked*; I caught that in testing and tightened it until it cited any time prior context informed a reply. I also had to *teach the OpenAI therapist model to be less "helpful"* in a crisis — its instinct was long supportive paragraphs, and I engineered the "high-intensity brevity" rule (fewer words, more directness) in the Playground because in a crisis less is more.
- **Structured project memory as a prompting strategy.** Instead of dumping context into each request, I maintained a set of markdown memory files and pointed **Claude Code** at them so it could reconstruct project state the way a new developer onboards. This was deliberate context engineering — and in one session it let Claude Code catch that my own notes were 20 days stale by cross-checking the git log.
- **A constrained, "explain-before-doing" workflow.** I explicitly instructed **Claude Code** to work one step at a time, explain each step, and wait for my approval. The removal of the guardian-notification system was executed as 10 ordered, individually-approved steps — a prompting discipline that kept a high-risk, multi-file change from breaking the app.

### 8.4 How I Verified the Correctness of What the AI Produced
I treated nothing any model generated as correct until I had checked it myself. My verification was layered (and is detailed further in §9):

- **Manual read-through of all clinical and prompt content.** Anything **Gemini** or **ChatGPT** produced as text a user would rely on clinically — the intake questions, the system-prompt language — I read 100% myself for relevance and safety.
- **Black-box / functional testing for code I couldn't fully read.** Since I was still learning JavaScript, I verified the *behavior* of **Claude Code's** code rather than every line: I deliberately tried to break the password rules, confirmed User A could not see User B's data, and exercised every validation path.
- **Playground stress-testing as a "difficult client."** I role-played an adversarial, resistant client against the system prompt in the **OpenAI Playground** and corrected the prompt before it ever reached code. This is how I found the brevity, reassurance-loop, and frame-integrity rules. I also cross-examined the prompt's behavior against **ChatGPT**.
- **Cross-model code audit.** I fed **Claude Code's** generated code to **Gemini** for a security and logic audit, then injected the findings back into Claude Code for refactoring. This loop caught **9 real backend bugs** — a JSON-mutation tracking bug that would have stopped intake forms from saving, a bulk-delete that bypassed cascades, missing cookie-security flags, a deprecated API call — none of which I would have caught alone at that stage. In later sessions I used **ChatGPT** the same way, as the independent second reader of Claude Code's output.
- **Running the real app and reading the logs.** For the safety-critical paths I ran the full flow and confirmed against the Flask server logs (e.g., that the `CRISIS_TRIGGER` line fired and the modal appeared). I did **not** take Claude Code's word that a feature worked.
- **Request/response auditing.** I watched the DevTools Network tab and the Flask terminal side by side to confirm payloads matched my models and to catch a double-fetch bug.

The honest lesson from verification: **the bugs that mattered were almost all caught by testing and real use, not by reading code.** The models wrote correct code for what they were asked — they could not tell me whether the *product behavior* was right. That was always my job.

### 8.5 What AI Did That I Couldn't Have Done vs. What Merely Saved Time
This distinction matters, and the answer is genuinely *both* — in different places.

**Things AI did that I could not have done on my own (at all, or at this pace):**
- **The entire JavaScript layer**, written by **Claude Code**. I started this project not knowing JS. The complex client-side state management — login sessions, data persistence, session restoration on refresh, the promise-based modal system — is work I could not have written myself. Claude Code didn't just speed this up; it made it *possible*.
- **Multi-file interdependency mapping.** Removing the guardian system meant tracing a web of dependencies — a model class, its relationship in `User`, foreign keys in other models, references in routes — where one missed reference produces hard-to-trace runtime errors. **Claude Code** held all of that in working memory across the change. I could not have reliably done that by hand at that speed.
- **Catching failure modes I hadn't considered.** **Claude Code** proactively added HTML-escaping to prevent an XSS hole in session text I never asked it to secure, flagged my stale memory notes, and correctly diagnosed a WSL-vs-Windows loopback confusion that was sending me down the wrong path.

**Things AI merely saved me time on (I could have done them, eventually) — all via Claude Code:**
- Hours of tedious CSS layout, glassmorphism, and responsive design.
- Mechanical sweeps like converting every `utcnow()` to `now(timezone.utc)` and appending `"Z"` to timestamps across seven call sites in five files.
- The modularization of the monolithic JS into ES modules.
- Writing the 26 individual test cases for the notification system.
- Configuration details I'd have eventually looked up (the `SEND_FILE_MAX_AGE_DEFAULT = 0` cache fix).

### 8.6 What I Relied on AI For Entirely, and the New Skills It Taught Me
**Relied on entirely:** the JavaScript logic, end to end, written by **Claude Code**. I directed *what* it should do and verified *that* it did it (black-box testing), but I did not write it and could not have. The frontend state machine exists because of Claude Code.

But "relying on it entirely" did not mean learning nothing — the opposite. I deliberately had **Claude Code implement a pattern and then explain it to me**, and that taught me skills I now genuinely understand:
- **Promise-based asynchronous patterns.** When Claude Code proposed `confirmModal()`/`alertModal()` that return Promises so calling code can `await` a user's choice, it implemented a pattern I'd have reached for callbacks instead. *Seeing it built and explained made the concept click in a way reading about it wouldn't have.*
- **Secure API communication.** By having **Claude Code** build and describe webhook **signature verification, ECDSA signatures, and idempotency** (in the notification system I later removed), I came to actually understand how secure, non-duplicating API communication works.
- **Full-stack data flow.** Working through **Claude Code's** code, I learned how data moves from a JS frontend, through a Flask REST API, into a PostgreSQL database — and how SQLAlchemy **cascades** make a single "wipe account" action clean up every related table without orphans.
- **Why architectural choices matter.** **Claude Code's** reasoning — e.g., *"therapy involves sitting with hard feelings, that is not unsafe"* as the principle behind a permissive safety reviewer — gave me language for design instincts I had but hadn't articulated.

This is, to me, the most interesting thing about how I used AI: **Claude Code** was not just a code generator, it was a **tutor I learned system design from by watching it work and asking it to explain.**

### 8.7 The Limits of AI — Where My Judgment Was Decisive
Equally important, and something I document carefully: **the tools implement direction cleanly, but the direction had to come from me — especially where the stakes mattered.** Concrete examples:

- **The crisis-detection gap.** After I had **Claude Code** tighten the triage prompt, I tested it by typing "I want to kill myself" — and the crisis modal *did not fire*. The rewritten prompt was internally logical but required a modifier (plan/means/timing) that a person in acute crisis wouldn't supply. The prompt was self-consistent; only **real-world testing** exposed the flaw. I identified the gap and directed the fix (a hardcoded list of direct statements that escalate on their own).
- **The safety-in-depth design call.** When I raised that the therapist and the triage system could disagree about crises, **Claude Code's** first proposal was to *remove* the therapist's ability to mention hotlines (single source of truth). I **pushed back** — that eliminates a backstop. The final layered design (tightened-but-not-removed AI guidance + triage + a keyword-sync backstop) was my architectural decision, which Claude Code then executed.
- **Safety continuity.** I reviewed a real transcript where the therapist accepted "it was a joke" after a violent statement and dropped a self-harm thread on deflection. I articulated the correct behavior (threads stay open until safety is confirmed; dark humor is data, not dismissal); **Claude Code** turned that into prompt language; I tested that it actually changed.
- **AI failed me at the moment I needed it most.** When my project directory was wiped during a migration to the **Cursor** editor (before I had made any Git commit), I first turned to **Gemini** to recover it — and its suggestions *made things worse* and contributed to a complete deletion. I stopped relying on it, used my own intuition (the app was still live in my browser), and manually extracted the rendered HTML/CSS/JS from the browser's DevTools. That taught me hard not to trust AI for critical system recovery.
- **Model-stability judgment.** A conversation with my father — who pointed out that for a *therapeutic* app, consistency matters more than cutting-edge dynamism — led me to reconsider running the product on the newest, most fluctuating **OpenAI** model and instead pin it to a specific, stable version. That's a domain-values judgment no model offered me.

This division — AI (and specifically Claude Code) as an exceptional implementer, context-holder, and tutor, and me as the source of design judgment, domain values, real-world testing, and crisis recovery — is the honest summary of how this project was built.

---

## 9. Validation & Quality Control

Demonstrating that the work was actually validated (not blindly accepted from any model) was a priority throughout. My validation methods:

### 9.1 Black-Box / Functional Testing
Rather than reading every line of **Claude Code's** generated JavaScript (a language I was learning), I tested behavior directly: deliberately trying to break the password requirements, confirming one user could not see another's data, triggering every validation path in the intake form.

### 9.2 Playground Stress-Testing the Prompts
I tested the therapist system prompt extensively in the **OpenAI Playground** by **role-playing a "difficult client"** — pushing on the persona, attempting to make it surrender the therapeutic frame, and probing crisis behavior — then correcting the prompt before moving it into code. This is how I discovered the "high-intensity brevity" rule (less talk, more directness in a crisis) and the reassurance-loop and frame-integrity safeguards.

### 9.3 End-to-End Application Testing
For the safety-critical paths I ran the *actual app* through the full flow (signup → intake → session → crisis message) and confirmed behavior against the **Flask server logs** (e.g., verifying the `CRISIS_TRIGGER` log line appeared and the modal rendered). I did not take **Claude Code's** word that a feature worked — I verified it myself.

### 9.4 Cross-Model Code Verification (the "Zero-Bug" loop)
This was my single most effective verification technique, and it was explicitly multi-model: code generated by **Claude Code** was handed to **Gemini** for a security and logic audit, and Gemini's findings were fed back into Claude Code for refactoring. (In later weeks I used **ChatGPT** the same way, as the independent second reader.) The **Gemini** audit caught **9 real backend bugs** before they could cause production failures, including:
- missing `flag_modified` for JSON-column mutation tracking (intake forms wouldn't have saved correctly),
- a bulk `DELETE` that bypassed ORM cascades (would have orphaned data / crashed on Postgres),
- missing production session-cookie security flags,
- a deprecated `User.query.get()` call.

### 9.5 Request/Response Auditing
During frontend integration I monitored the **DevTools Network tab** to confirm HTTP methods and JSON payloads matched the SQLAlchemy models, cross-referenced browser console output against the Flask terminal in real time (catching a double-fetch bug), and tested status-code handling (401 → login redirect, intake gatekeeping).

### 9.6 Manual Read-Through of Clinical Content
All textual output from **ChatGPT** and **Gemini** destined for clinical use (the intake questions, the system-prompt language) got a 100% manual read-through for clinical relevance and safety.

**Key reflection on validation:** the bugs that mattered most were almost all caught through *testing and real use*, not code review. Claude Code wrote correct code for what it was asked — it could not judge whether the overall product behavior was right. That judgment was consistently my responsibility.

---

## 10. The Development Journey: Pivots, Setbacks, and Removed Work

This project was not a straight line. The path — including the dead ends — is itself evidence of effort and judgment. *Items marked **[Removed]** were built and validated but deliberately cut from the final product.*

### 10.1 Architectural Evolution
1. **Single-file client-side prototype** — the app began as one HTML file with inline JS, storing all data in browser `localStorage`, with a progressive login-lockout system and client-side "user isolation." **[Superseded]** by the backend rewrite; abuse protection now comes from server-side rate limiting.
2. **Flask + SQLAlchemy backend rewrite** — a complete re-architecture into a real web server with a relational database, secure password hashing, and a REST API, because the client-side approach couldn't provide persistence, real security, or scalability.
3. **App-factory + ES-module modularization** — `app.py` split into `config.py`/`extensions.py`/blueprints; the monolithic `app.js` broken into focused ES modules.
4. **Auth upgrade** — Flask-Login + Flask-Bcrypt replaced by **Flask-Security-Too** token auth, plus the HIBP breach check.

### 10.2 The Data-Loss & Recovery Incident
Early on, while migrating my workflow from **Claude Code** to the **Cursor** editor, an automated "undo"/sync in Cursor wiped the local project directory **before I had made any Git commits**. I recovered the application by **manually extracting the still-running HTML/CSS/JS from the browser's developer tools**. Notably, I first tried to use **Gemini** to recover it and its suggestions made things *worse* — a turning point that taught me not to rely on AI for critical system recovery. I immediately initialized a Git repository and have used version control ever since. This is why the very first commits in the history are literally titled "Recovered lol."

### 10.3 The Guardian-Notification System — Built, Then Removed **[Removed]**
I designed and implemented a complete external emergency-alert pipeline: **Twilio SMS** and **SendGrid email** services to notify a user's guardian on a crisis trigger, with webhook signature verification, ECDSA signatures, idempotency/deduplication, background-threaded retries, and a suite of **26 tests**. After reflection, I removed the entire subsystem and replaced it with a **user-facing crisis modal**. The removal required careful interdependency mapping (deregistering the blueprint before deleting its file, stripping fields from multiple models, cascading cleanup) — done as 10 individually-approved steps. This decision reflects a values judgment about appropriate, non-intrusive crisis handling for this product.

### 10.4 The Deployment Odyssey — Explored, Then Abandoned **[Removed]**
I attempted to deploy on a free tier across **Render, Railway, Neon + Koyeb, and PythonAnywhere**, hitting cost limits, expiring credits, a Python 3.10 dependency incompatibility (leftover data-science packages), and stale-cache issues. I ultimately decided the project would run **locally against a hosted Neon Postgres database**, and removed the deployment configs (`render.yaml`, `Procfile`). This let me focus the remaining effort on product quality rather than fighting hosting platforms.

### 10.5 Speculative Schema, Trimmed **[Removed]**
An intermediate design had 9 tables (`guardian_profiles`, `assignments`, `journal_entries`, `analytics_snapshots`, plus emergency-alert tables). These were cut when their features were removed or deferred, leaving the lean 7-table final schema.

### 10.6 A Behavior Feature That Didn't Make the Cut **[Removed]**
A "PATTERN ALERT" system (injecting a warning into the therapist's context if a user skipped or failed a goal three times in a row) was discussed and partially specified, but is **not** in the final build. A lighter cue survives: the greeting endpoint notes when a *substantive* prior session ended without setting any goal.

---

## 11. Engineering Challenges & How I Solved Them

A selection of the hardest, most instructive bugs — each one a case study in AI-assisted debugging plus human validation.

### 11.1 "The AI Has No Memory" — Which Was Actually a Safety-Filter Bug
**Symptom:** the AI therapist (GPT-4.1) seemed to forget what was said earlier in the same conversation. **My assumption:** message history wasn't persisting. Working with **Claude Code**, a structured diagnostic (Network tab → server-side logging → direct DB query) revealed two surprises: (1) `DATABASE_URL` actually pointed at a live **Neon Postgres** instance, not local SQLite — the messages were there all along; (2) the real bug was in the safety-review branch logic:

```python
if review["verdict"] in ("APPROVE", "REVISE"):
    reply = review["safe_response"] or SAFE_FALLBACK_MESSAGE
```

This substituted the safety model's *rewritten* version for **every** reply — even on `APPROVE` ("this is fine as-is") — making all output sound sanitized and flat (which read as "no memory"). **Fix:** I had **Claude Code** split the branches so `APPROVE` keeps the original draft and only `REVISE` substitutes. Claude Code also rewrote the safety-review prompt from ~160 lines of tonal nitpicking down to ~25 lines focused only on genuine harm, on the principle that *"therapy involves sitting with hard feelings — that is not unsafe."*

### 11.2 "I Want to Kill Myself" Didn't Trigger the Crisis Modal
After I had **Claude Code** tighten the triage prompt, a direct suicidal statement with no qualifier fell through to `POSSIBLE_HARM`. **Fix:** a hardcoded list of direct statements that escalate to `CLEAR_IMMEDIATE_RISK` on their own. Caught only by my own real-world testing.

### 11.3 Every Message Was Treated as a Risk
The triage system had no benign output — `POSSIBLE_HARM` was the fallback, so even "hi" pushed the app into a guarded mode. **Fix:** I directed **Claude Code** to add a `NO_RISK` default with a short-circuit in the policy engine, a change it coordinated across four files (prompt, parser, engine constants, route validator).

### 11.4 Timezone Display Bug
Timestamps stored as naive UTC were serialized with `.isoformat()` (no zone marker) and parsed by the browser as *local* time, so 15:30 UTC displayed as 3:30 PM instead of 10:30 AM NY. **Fix:** append `"Z"` to all `isoformat()` outputs — **Claude Code** applied this across seven call sites in five route files.

### 11.5 Recurring Cache Gremlins
Two separate caching issues: Flask's **Jinja2 template cache** served stale HTML after edits (fixed by a server restart, after **Claude Code** correctly ruled out a WSL/Windows loopback red herring I had been chasing), and the **browser static-file cache** served stale JS (permanently fixed with `SEND_FILE_MAX_AGE_DEFAULT = 0`).

### 11.6 XSS in Session Labels
**Claude Code** proactively flagged that concatenating unsanitized session summaries into `innerHTML` was an injection risk, and added HTML-escaping — a vulnerability I would likely have caught only in later review.

---

## 12. Skills Acquired

Despite (and because of) heavy AI use, I came away with concrete, transferable knowledge:
- **Full-stack data flow** — how a JS frontend talks to a Flask REST API and into a PostgreSQL database asynchronously.
- **Relational modeling & integrity** — SQLAlchemy relationships, cascade deletes, foreign-key constraints, and why a bulk delete is dangerous.
- **Prompt engineering as a discipline** — personas, CoT, few-shot, cross-model verification, and iterative stress-testing.
- **AI system design** — orchestrating multiple models in a deterministic, fail-safe pipeline rather than trusting a single model.
- **Secure API communication** — token auth, cookie hardening, k-anonymity breach checking, prompt-injection defense, webhook signatures/idempotency (from the notification system I built and removed).
- **Configuration & environment management** — secrets, environment-aware settings, cache control, DB URL portability.
- **Version control discipline** — learned the hard way after the data-loss incident.
- **The judgment to know what AI is good and bad at** — and to stay in the loop on the decisions that matter.

---

## 13. Current State & Future Work

**Current state:** ZenShell is a complete, working, end-to-end application running locally against Neon Postgres. The full flow — signup → intake → pre-check → AI session with the live safety pipeline → goal wrap-up → post-check → dashboard, with cross-session memory and a crisis modal — is functional.

**Known open items / future work:**
- End-to-end verification of the pre-check goal check-in across the skip/continue paths.
- Decide whether the post-check editable goal should be removed so the chat is the single source of truth for goal refinement (to prevent silent drift).
- Dead-code/cleanup pass (e.g., a leftover diagnostic log line; an unused 0-byte local SQLite file).
- Possible model-version pinning for behavioral consistency (a stability consideration raised during prompt development).
- Longer-term: real-time empathetic feedback during intake; richer progress analytics.

---

## Appendix A: API Endpoint Registry

| Endpoint | Method | Function |
|---|---|---|
| `/api/signup` | POST | Create account (server-side validation, bcrypt hash) |
| `/api/login` | POST | Authenticate; return token + intake status |
| `/api/logout` | POST | End session |
| `/api/me` | GET | Current user info |
| `/api/account` | DELETE | Wipe account + all cascaded data |
| `/api/intake` | GET | Fetch saved intake |
| `/api/intake` | POST | Save intake (draft or final) |
| `/api/sessions` | GET | List user's sessions |
| `/api/sessions` | POST | Start a session (with optional prior-goal check-in) |
| `/api/sessions` | DELETE | Delete selected or all sessions (ORM loop) |
| `/api/sessions/<id>` | GET | Get one session + full chat history |
| `/api/sessions/<id>/greeting` | POST | AI-generated opening greeting |
| `/api/sessions/<id>/wrap-up` | POST | AI proposes a next-session goal |
| `/api/sessions/<id>/complete` | POST | Finalize session; generate AI summary |
| `/api/chat` | POST | The orchestrator: triage → policy → generate → review → persist (rate-limited 30/min, 200/day) |

## Appendix B: Database Schema
7 tables: `roles`, `users`, `intake_profiles`, `therapy_sessions`, `chat_messages`, `safety_alerts`, `user_risk_states`, plus the `user_roles` association table. (See §6.)

## Appendix C: Commit Timeline
18 commits, Feb 18 → May 28, 2026. Abbreviated arc:
- **Recovered lol / Recovered UI from browser** — the data-loss recovery and first version control.
- **Add entry/exit slips, GPT-4.1 integration, security fixes** — first AI integration.
- **Transition to Flask + GPT-4.1 backend** / **Clean up old files** — the client-side → backend rewrite.
- **Add rate limiting to /api/chat**.
- **Refactor to modular Flask app + full safety pipeline** — app factory + the triage/policy/review pipeline.
- **Add emergency notification system (Twilio + SendGrid)** → later **Replace parent notifications with crisis modal + add goal-setting flow** — the build-then-remove arc.
- **Add Procfile for Koyeb deployment** / **Remove unused data science dependencies** — the deployment odyssey.
- **Add AI greeting endpoint + goal-disengagement detection**.
- **Tighten therapist prompt** / **Restrict session summaries to client-originated content only** — the final prompt-tuning passes.

---

*Report generated from a full audit of the submitted source code, cross-referenced against ten weekly progress reports. Features described in §3 reflect the verified final codebase; explored-and-removed work is documented in §10 and labeled accordingly.*
