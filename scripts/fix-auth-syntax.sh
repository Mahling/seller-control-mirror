#!/usr/bin/env bash
set -euo pipefail

# --- 1) main.py bereinigen & SessionMiddleware korrekt registrieren ---
python3 - <<'PY'
import re, pathlib, os
p = pathlib.Path("/opt/seller-control/backend/app/main.py")
s = p.read_text(encoding="utf-8")
orig = s

# a) korrekten Import sicherstellen
if "from starlette.middleware.sessions import SessionMiddleware" not in s:
    m = re.search(r"^(?:from\s+\S+\s+import\s+.+|import\s+.+)(?:\n(?:from\s+\S+\s+import\s+.+|import\s+.+))*", s, re.M)
    pos = m.end() if m else 0
    s = s[:pos] + "\nfrom starlette.middleware.sessions import SessionMiddleware\n" + s[pos:]

# b) alte/kaputte SessionMiddleware-Registrierungen (auch mehrzeilig) entfernen
s = re.sub(r"\n?\s*app\.add_middleware\(\s*SessionMiddleware\b[\s\S]*?\)\s*", "\n", s)

# c) evtl. übrig gebliebene, einzelne ')' Zeilen entfernen
s = re.sub(r"^\s*\)\s*$", "", s, flags=re.M)

# d) EIN sauberes add_middleware direkt nach app = FastAPI(...)
m = re.search(r"app\s*=\s*FastAPI\([^)]*\)", s)
insert = "\napp.add_middleware(SessionMiddleware, secret_key=os.environ.get('SESSION_SECRET', 'changeme'), same_site='lax')\n"
if m:
    s = s[:m.end()] + insert + s[m.end():]
else:
    s = insert + s  # Fallback

# e) 'os' importieren falls nötig
if not re.search(r'^\s*import\s+os\b', s, re.M):
    s = "import os\n" + s

if s != orig:
    p.write_text(s, encoding="utf-8")
    print("Patched main.py")
else:
    print("No changes to main.py")
PY

# --- 2) SESSION_SECRET in .env sicherstellen (nicht committen) ---
if ! grep -q '^SESSION_SECRET=' /opt/seller-control/.env 2>/dev/null; then
  echo "SESSION_SECRET=$(openssl rand -hex 24)" >> /opt/seller-control/.env
fi

# --- 3) Commit & Push (nur Code) ---
cd /opt/seller-control
git add backend/app/main.py || true
git commit -m "auth: normalize SessionMiddleware registration & remove stray parenthesis" || true
git push || true

# --- 4) Build & Deploy + Live-Logs ---
/opt/seller-control/update.sh -l
