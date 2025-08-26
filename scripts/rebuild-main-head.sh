#!/usr/bin/env bash
set -euo pipefail

FILE="/opt/seller-control/backend/app/main.py"
[ -f "$FILE" ] || { echo "❌ $FILE nicht gefunden"; exit 1; }

python3 - <<'PY'
import re, os
from pathlib import Path

p = Path("/opt/seller-control/backend/app/main.py")
s = p.read_text(encoding="utf-8")
orig = s

# Normalisiere Zeilenenden
s = s.replace("\r\n", "\n")

# 1) Aufräumen: alles vor dem ersten Import/From weghauen (falls durch frühere Patches Müll am Start steht)
m = re.search(r'(?m)^(?:\s*"""[\s\S]*?"""\s*\n|\s*#.*\n)*\s*(?=(from|import)\s)', s)
if m:
    s = s[m.start():]

# 2) Importblock einsammeln
lines = s.split("\n")
imports = []
rest_index = 0
for i, line in enumerate(lines):
    if line.strip().startswith("from ") or line.strip().startswith("import "):
        imports.append(line)
    elif line.strip() == "":
        imports.append(line)
    else:
        rest_index = i
        break

rest = "\n".join(lines[rest_index:])

# 3) Pflicht-Imports hinzufügen (ohne Duplikate)
need = [
    "import os",
    "from fastapi import FastAPI, Request, Form, Depends, status",
    "from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse",
    "from fastapi.middleware.cors import CORSMiddleware",
    "from starlette.middleware.sessions import SessionMiddleware",
]
def dedupe_keep_order(seq):
    seen=set(); out=[]
    for x in seq:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

imports = [ln for ln in imports if ln.strip() != ""]
imports = dedupe_keep_order(imports + need)

# 4) Alte/kaputte App-Initialisierung und doppelte SessionMiddleware entfernen
rest = re.sub(r'(?ms)^\s*app\s*=\s*FastAPI\s*\([^)]*\)\s*', '', rest)
rest = re.sub(r'(?ms)^\s*app\.add_middleware\(\s*SessionMiddleware[\s\S]*?\)\s*', '', rest)

# 5) Vereinzelte hängende ")" Zeilen killen
rest = re.sub(r'(?m)^\s*\)\s*$', '', rest)

# 6) Neue, saubere Kopfsektion bauen
head = "\n".join(imports) + "\n\n"
head += "app = FastAPI()\n"
head += "app.add_middleware(SessionMiddleware, secret_key=os.environ.get('SESSION_SECRET','changeme'), same_site='lax')\n"

# 7) Zusammensetzen & schreiben
out = head + "\n" + rest
p.write_text(out, encoding="utf-8")
print("✅ main.py Kopf neu aufgebaut.")
PY

# 2) SESSION_SECRET in .env absichern (wird NICHT committed)
if ! grep -q '^SESSION_SECRET=' /opt/seller-control/.env 2>/dev/null; then
  echo "SESSION_SECRET=$(openssl rand -hex 24)" | sudo tee -a /opt/seller-control/.env >/dev/null
  echo "🔐 SESSION_SECRET ergänzt."
fi

# 3) Commit & Push (nur Code)
cd /opt/seller-control
git add backend/app/main.py || true
git commit -m "chore(auth): rebuild main.py head & install SessionMiddleware before auth guard" || true
git push || true

# 4) Build & Deploy + Logs
/opt/seller-control/update.sh -l
