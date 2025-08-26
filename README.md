# Seller-Control Dashboard (Multi-Account) — MVP

FastAPI + PostgreSQL + Tailwind/HTMX (no Node required). Multi-account SP-API scaffold for:
- Orders (live pull placeholder)
- Customer Returns (via Reports API — stubbed hooks)
- Removals/Returns-to-You (via Reports API — stubbed hooks)
- Inventory Ledger & Reimbursements (via Reports API — stubbed hooks)
- Recon view: Lost/Damaged vs Reimbursed (placeholder aggregation)

> This is a *working scaffold* with DB models, REST endpoints and a lightweight dashboard UI.
> SP-API calls are stubbed — plug your credentials and replace the stubs in `app/sp_api.py`.

## Quick Start (Docker)
1. Copy env file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` (Postgres password, region, LWA credentials).
3. Start services:
   ```bash
   docker compose up --build
   ```
4. Open: http://localhost:8088  (dashboard)
5. Swagger: http://localhost:8088/docs

## Local (Python)
```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cp .env.example .env
# start postgres yourself or adjust DB URL in .env
uvicorn app.main:app --reload --port 8088 --app-dir backend
```

## What to customize next
- Implement real SP-API logic in `backend/app/sp_api.py` (using your credentials).
- Add scheduled jobs in `backend/app/scheduler.py` for periodic report fetches.
- Expand `recon` logic in `backend/app/services.py` to match your exact policy.
- Harden auth (this MVP has no user login — add OAuth if needed).
