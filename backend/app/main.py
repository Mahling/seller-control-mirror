import os, sys, pathlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# ------------------------------------------------------------
# DB-Session beschaffen (robust, mit Fallback)
# ------------------------------------------------------------
def _obtain_sessionlocal():
    # 1) Normalfall: aus app.database importieren
    try:
        from app.database import SessionLocal as SL  # type: ignore
        return SL
    except Exception:
        pass

    # 2) Alternativ: aus database.py im selben Verzeichnis
    try:
        from database import SessionLocal as SL  # type: ignore
        return SL
    except Exception:
        pass

    # 3) Fallback: selbst Engine bauen (aus Env)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        pg_user = os.getenv("POSTGRES_USER", "postgres")
        pg_pass = os.getenv("POSTGRES_PASSWORD", "postgres")
        pg_host = os.getenv("POSTGRES_HOST", "db")
        pg_port = os.getenv("POSTGRES_PORT", "5432")
        pg_db   = os.getenv("POSTGRES_DB", "postgres")
        db_url = f"postgresql+psycopg2://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"

    engine = create_engine(db_url, pool_pre_ping=True, future=True)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)

SessionLocal = _obtain_sessionlocal()

# ------------------------------------------------------------
# Optionale Imports (tolerant)
# ------------------------------------------------------------
try:
    from app.auth import verify_user_credentials  # (db, username_or_email, password) -> user|None
except Exception:
    verify_user_credentials = None

try:
    from app.sp_api_reports_patch import (
        fetch_returns_rows,
        fetch_removals_rows,
        fetch_adjustments_rows,
        fetch_reimbursements_rows,
    )
except Exception:
    fetch_returns_rows = fetch_removals_rows = fetch_adjustments_rows = fetch_reimbursements_rows = None

# ------------------------------------------------------------
# FastAPI & Middleware
# ------------------------------------------------------------
app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "changeme"),
    same_site="lax",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {"/login", "/api/login", "/health"}

class AuthGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/static"):
            return await call_next(request)
        uid = request.session.get("uid") if "session" in request.scope else None
        if not uid:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
            return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
        return await call_next(request)

app.add_middleware(AuthGuard)

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
from sqlalchemy.orm import Session
from sqlalchemy import text

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}

LOGIN_FORM_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Login</title></head>
<body>
  <h2>Login</h2>
  <form method="post" action="/api/login">
    <label>E-Mail oder Benutzername <input name="username" required /></label><br/>
    <label>Passwort <input type="password" name="password" required /></label><br/>
    <button type="submit">Einloggen</button>
  </form>
</body></html>"""

@app.get("/login", response_class=HTMLResponse)
def login_form():
    return HTMLResponse(LOGIN_FORM_HTML)

@app.post("/api/login")
def login_api(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user_id: Optional[int] = None

    # 1) Bevorzugt: vorhandene verify_user_credentials
    if verify_user_credentials:
        try:
            user = verify_user_credentials(db, username, password)
            if user:
                user_id = int(getattr(user, "id", 0))
        except Exception:
            user_id = None

    # 2) Fallback: direkte SQL + passlib
    if not user_id:
        try:
            from passlib.hash import bcrypt
            row = db.execute(
                text("SELECT id, password_hash FROM users WHERE username=:u OR email=:u LIMIT 1"),
                {"u": username},
            ).mappings().first()
            if row and row.get("password_hash") and bcrypt.verify(password, row["password_hash"]):
                user_id = int(row["id"])
        except Exception:
            user_id = None

    if not user_id:
        return HTMLResponse("<h3>Login fehlgeschlagen</h3><a href='/login'>Zurück</a>", status_code=401)

    request.session["uid"] = user_id
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    uid = request.session.get("uid")
    return HTMLResponse(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Seller Control</title></head>
<body>
  <h1>Seller Control</h1>
  <p>Eingeloggt als User-ID: {uid}</p>
  <form action="/api/reports/pull?account_id=1" method="post">
    <button type="submit">Pull reports</button>
  </form>
  <p><a href="/logout">Logout</a></p>
</body></html>"""
    )

def _find_refresh_token(db: Session, account_id: int) -> Optional[str]:
    # ORM
    try:
        from app.models import AmazonAccount  # type: ignore
        acc = db.get(AmazonAccount, account_id)
        if acc and getattr(acc, "refresh_token", None):
            return acc.refresh_token
    except Exception:
        pass
    # Raw SQL – mehrere mögliche Tabellennamen testen
    for table in ("amazon_accounts", "accounts", "seller_accounts"):
        try:
            row = db.execute(
                text(f"SELECT refresh_token FROM {table} WHERE id=:id LIMIT 1"),
                {"id": account_id},
            ).mappings().first()
            if row and row.get("refresh_token"):
                return row["refresh_token"]
        except Exception:
            continue
    return None

@app.post("/api/reports/pull")
def api_pull_reports(account_id: int, db: Session = Depends(get_db)):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    safe_start = start.date().isoformat()
    safe_end = end.date().isoformat()

    enc_refresh = _find_refresh_token(db, account_id)
    if not enc_refresh:
        return JSONResponse(
            {"returns": 0, "removals": 0, "adjustments": 0, "reimbursements": 0,
             "note": f"Kein refresh_token für account_id={account_id} gefunden."},
            status_code=200,
        )

    if not all([fetch_returns_rows, fetch_removals_rows, fetch_adjustments_rows, fetch_reimbursements_rows]):
        return JSONResponse({"detail": "Report-Funktionen nicht verfügbar – bitte Code/Import prüfen."}, status_code=500)

    try:
        rets = fetch_returns_rows(account_id, enc_refresh, safe_start, safe_end) or []
        rems = fetch_removals_rows(account_id, enc_refresh, safe_start, safe_end) or []
        adjs = fetch_adjustments_rows(account_id, enc_refresh, safe_start, safe_end) or []
        reim = fetch_reimbursements_rows(account_id, enc_refresh, safe_start, safe_end) or []
        return {"returns": len(rets), "removals": len(rems), "adjustments": len(adjs), "reimbursements": len(reim)}
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)
