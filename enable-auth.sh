#!/usr/bin/env bash
set -euo pipefail
cd /opt/seller-control

# --- 0) Secret setzen (einmalig sinnvoll) ---
if ! grep -q '^SESSION_SECRET=' .env 2>/dev/null; then
  echo "SESSION_SECRET=$(openssl rand -hex 32)" >> .env
  echo "ℹ️  SESSION_SECRET in .env ergänzt."
fi

# --- 1) requirements: passlib fürs Hashing ---
REQ="backend/requirements.txt"
grep -q '^passlib\[bcrypt\]' "$REQ" || echo 'passlib[bcrypt]==1.7.4' >> "$REQ"

# --- 2) auth.py schreiben (Hashing + DB-Helfer) ---
cat > backend/app/auth.py <<'PY'
from typing import Optional, Mapping
from sqlalchemy import text
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.verify(password, password_hash)
    except Exception:
        return False

def ensure_users_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS sc_users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """))
    db.commit()

def find_user(db: Session, login: str) -> Optional[Mapping]:
    row = db.execute(
        text("""SELECT id, email, username, password_hash, is_active
                FROM sc_users
                WHERE email=:l OR username=:l
                LIMIT 1"""),
        {"l": login},
    ).mappings().first()
    return row

def create_user(db: Session, email: str, username: str, password: str) -> int:
    ph = hash_password(password)
    row = db.execute(
        text("""INSERT INTO sc_users(email, username, password_hash)
                VALUES (:e, :u, :p)
                ON CONFLICT DO NOTHING
                RETURNING id"""),
        {"e": email, "u": username, "p": ph},
    ).first()
    if row is None:
        # User existiert schon – ID zurückgeben
        row2 = db.execute(
            text("SELECT id FROM sc_users WHERE email=:e OR username=:u"),
            {"e": email, "u": username},
        ).first()
        db.commit()
        return int(row2[0])
    db.commit()
    return int(row[0])
PY

# --- 3) main.py patch: Sessions, Middleware, Login/Logout/Me, /login-HTML ---
PYFILE="backend/app/main.py"
cp -a "$PYFILE" "${PYFILE}.bak.$(date +%s)"

# Anhängen (ohne bestehende App zu ändern)
python3 - <<'PY'
import os
from pathlib import Path
p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")

block = r'''
# ======== AUTH & SESSIONS (appended) ========
import os
from fastapi import Request, Form, Depends
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session as SASession
from .auth import ensure_users_table, find_user, verify_password

# Session-Cookies signieren
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "change-me-please"))

# Guard-Middleware: ohne Login -> redirect /login (HTML) bzw. 401 (API)
@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    path = request.url.path
    public = (
        path == "/login"
        or path.startswith("/docs")
        or path.startswith("/openapi.json")
        or path.startswith("/api/auth/")
        or path.startswith("/favicon")
        or path == "/healthz"
        # statics, wenn du welche hast:
        or path.startswith("/static")
    )
    if public:
        return await call_next(request)
    if request.session.get("uid"):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return RedirectResponse("/login", status_code=302)

# kleine Helfer
def _get_db():
    # nutzt dein bestehendes get_db-Dependency
    from .main import get_db as _gdb   # type: ignore
    return _gdb

def _login_page(msg: str = "") -> str:
    return f"""<!doctype html>
<html lang='de'><head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>Login · Seller-Control</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head><body class="bg-gray-50 min-h-screen flex items-center justify-center">
  <form method="post" action="/login" class="bg-white shadow rounded-2xl p-6 w-full max-w-md space-y-4">
    <h1 class="text-xl font-semibold text-center">Anmeldung</h1>
    {('<div class="text-red-600 text-sm text-center">'+msg+'</div>') if msg else ''}
    <div>
      <label class="block text-sm text-gray-600 mb-1">E-Mail oder Benutzername</label>
      <input name="login" class="w-full border rounded-lg px-3 py-2" placeholder="you@example.com" required>
    </div>
    <div>
      <label class="block text-sm text-gray-600 mb-1">Passwort</label>
      <input name="password" type="password" class="w-full border rounded-lg px-3 py-2" required>
    </div>
    <button class="w-full bg-black text-white rounded-lg py-2">Einloggen</button>
  </form>
</body></html>"""

@app.get("/login", response_class=HTMLResponse)
def login_form(db: SASession = Depends(get_db)):
    # sicherstellen, dass Tabelle existiert
    ensure_users_table(db)
    return HTMLResponse(_login_page())

@app.post("/login")
def login_submit(request: Request, login: str = Form(...), password: str = Form(...), db: SASession = Depends(get_db)):
    ensure_users_table(db)
    u = find_user(db, login)
    if not u or not u["is_active"] or not verify_password(password, u["password_hash"]):
        return HTMLResponse(_login_page("Anmeldung fehlgeschlagen."), status_code=401)
    request.session["uid"] = int(u["id"])
    return RedirectResponse("/", status_code=302)

@app.post("/api/auth/logout")
@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    # für API und Form gleichermaßen sinnvoll
    if request.headers.get("accept", "").startswith("application/json"):
        return {"ok": True}
    return RedirectResponse("/login", status_code=302)

@app.get("/api/auth/me")
def me(request: Request, db: SASession = Depends(get_db)):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    row = db.execute(
        text("SELECT id, email, username FROM sc_users WHERE id=:i"),
        {"i": uid},
    ).mappings().first()
    return row or JSONResponse({"detail": "not found"}, status_code=404)
# ======== END AUTH ========
'''
# imports that block uses
if "from sqlalchemy import text" not in s:
    s = s.replace("from datetime import", "from sqlalchemy import text\nfrom datetime import")

if "AUTH & SESSIONS (appended)" not in s:
    s += "\n" + block + "\n"

p.write_text(s, encoding="utf-8")
print("✅ main.py erweitert (Sessions, Middleware, Login/Logout/Me).")
PY

# --- 4) Commit + Push + Deploy + Logs ---
git add backend/requirements.txt backend/app/auth.py backend/app/main.py
git commit -m "feat(auth): classic login (bcrypt), session middleware, guard, /login"
git push origin main

/opt/seller-control/update.sh -l
