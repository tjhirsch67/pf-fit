# PF Coach — concept demo

> An intelligent coaching layer concept for Planet Fitness members. **Not affiliated with,
> endorsed by, or approved by Planet Fitness.** This is a pitch/prototype artifact — see
> `CLAUDE.md` §10 (Guardrails) before generating any branding or assets.

PF Coach turns the PF equipment floor into a guided, rotating, progress-tracked program
sold as a low-cost add-on. It starts maximally prescriptive (the **Guided** Express Circuit)
and hands control to the member as they earn confidence (the **autonomy gradient**:
guided → coached → self-directed).

## Architecture

| Layer | Tech |
|---|---|
| Backend | FastAPI (Python 3.11), SQLAlchemy 2 + Alembic |
| Database | PostgreSQL (Railway) |
| Frontend | Vanilla HTML/CSS/JS, mobile-first PWA (Netlify) |
| AI | Anthropic API (intake reasoning, program generation, advisory) |
| Auth | JWT (bearer) + bcrypt |
| Email | Mailtrap (HTTP API) |

The two load-bearing decisions live in `Schema.md`: the **measurement-type taxonomy** and
the **indexed-progress math** (every exercise normalized to its own first session = 100, so
pattern-trends survive weekly rotation).

## Repo layout

```
PF/
├── CLAUDE.md          # project context (auto-loaded each session)
├── Design.md          # visual/UX system — read before frontend work
├── Schema.md          # data model — source of truth for the DB layer
├── Seed.md            # reference vs. demo data plan
├── backend/
│   ├── main.py            # FastAPI app + router registration
│   ├── config.py          # pydantic-settings
│   ├── database.py        # engine / session / get_db
│   ├── auth.py            # JWT + bcrypt + role guards
│   ├── models.py          # SQLAlchemy ORM (source of truth for tables)
│   ├── progress.py        # indexed-gains engine (the hero metric)
│   ├── rotation.py        # club-aware rotation + swap engine
│   ├── migrations/        # Alembic
│   ├── routers/           # API routers
│   └── scripts/seed.py    # idempotent reference + --demo seed
└── frontend/          # PWA (built after the backend foundation)
```

## Local development

```powershell
# 1. Create a Python 3.11 virtual environment (the pinned stack lacks 3.14 wheels)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r backend\requirements.txt

# 3. Configure environment
copy backend\.env.example backend\.env   # then fill in values

# 4. Run migrations
cd backend
alembic upgrade head

# 5. Seed reference data (+ optional demo user)
python scripts\seed.py            # reference data only
python scripts\seed.py --demo     # + the fabricated demo user with 8 weeks of history

# 6. Run the API
uvicorn main:app --reload
```

## Deployment

| Layer | URL |
|---|---|
| Frontend (PWA) | https://pf-fit.netlify.app |
| Backend (API) | https://pf-fit-production.up.railway.app |
| Repo | https://github.com/tjhirsch67/pf-fit |

**Demo login:** `demo@pfcoach.app` / `demo1234` (or tap "explore the demo" on the login screen).

- **Backend** → Railway. Builder: **Nixpacks**, Root Directory: `backend`, `NIXPACKS_PYTHON_VERSION=3.11`.
  Env vars: `DATABASE_URL` (Postgres reference), `SECRET_KEY`, `ANTHROPIC_API_KEY`. The `Procfile`
  runs `alembic upgrade head` on every boot. Seed once via a Pre-deploy Command
  (`python scripts/seed.py --demo`), then clear it.
- **Frontend** → Netlify. Publish directory: `frontend`, no build command. The API base lives in
  `frontend/js/config.js`. `_headers` ships a CSP locked to the API origin.
- **Database** → Railway PostgreSQL (migrations run automatically via the `Procfile`).
