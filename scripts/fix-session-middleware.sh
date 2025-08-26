#!/usr/bin/env bash
set -euo pipefail

FILE="/opt/seller-control/backend/app/main.py"

echo "🔧 Patching $FILE …"
python3 - <<'PY'
import os, re, pathlib
p = pathlib.Path("/opt/seller-control/backend/app/main.py")
s = p.read_text(encoding="utf-8")
changed = False

# 0) Entferne evtl. "verirrte" Einzelzeile 'SessionMiddleware,' (so wie im Log zu sehen)
s2 = re.sub(r'^\s*SessionMiddleware,?\s*$', '', s, flags=re.M)
if s2 != s:
    s = s2
    changed = True

# 1) Falls jemand fälschlich aus fastapi.middleware SessionMiddleware importiert hat, entferne es dort
def strip_sm_from_fastapi_group(src: str) -> str:
    pat = re.compile(r'(from\s+fastapi\.middleware\s+import\s*\()(.*?)(\))', re.S)
    def repl(m):
        inner = m.group(2)
        # robust trennen, Kommentare/Whitespace tolerieren
        parts = [x.strip() for x in re.split(r',(?![^\(\)]*\))', inner)]
        parts = [x for x in parts if x and x != 'SessionMiddleware']
        return m.group(1) + ', '.join(parts) + m.group(3)
    return pat.sub(repl, src)

s2 = strip_sm_from_fastapi_group(s)
if s2 != s:
    s = s2
    changed = True

# 2) Korrektes Import-Statement sicherstellen
if "from starlette.middleware.sessions import SessionMiddleware" not in s:
    # Nach dem ersten Importblock einfügen
    m = re.search(r"^(?:from\s+\S+\s+import\s+.+|import\s+.+)(?:\n(?:from\s+\S+\s+import\s+.+|import\s+.+))*", s, re.M)
    insert_at = m.end() if m else 0
    s = s[:insert_at] + "\nfrom starlette.middleware.sessions import SessionMiddleware\n" + s[insert_at:]
    changed = True

# 3) 'import os' falls benötigt
if "import os" not in s:
    s = "import os\n" + s
    changed = True

# 4) Vorhandene falsche/alte SessionMiddleware-Registrierungen entfernen (doppelt vermeiden)
s2 = re.sub(r"\n\s*app\.add_middleware\(\s*SessionMiddleware\b.*?\)\s*", "\n", s, flags=re.S)
if s2 != s:
    s = s2
    changed = True

# 5) SessionMiddleware als LETZTES adden (läuft dann als erstes und setzt request.session)
insert_line = "\napp.add_middleware(SessionMiddleware, secret_key=os.environ.get('SESSION_SECRET', 'changeme'), same_site='lax')\n"

last = None
for m in re.finditer(r"\n\s*app\.add_middleware\(", s):
    last = m
if last:
    pos = last.end()
    s = s[:pos] + insert_line + s[pos:]
else:
    m = re.search(r"app\s*=\s*FastAPI\([^)]*\)", s)
    pos = m.end() if m else 0
    s = s[:pos] + insert_line + s[pos:]

changed = True

p.write_text(s, encoding="utf-8")
print("✅ main.py gepatcht.")
PY

# 6) SESSION_SECRET in .env absichern (nie ins Repo committen)
if ! grep -q '^SESSION_SECRET=' /opt/seller-control/.env 2>/dev/null; then
  echo "🔐 SESSION_SECRET fehlt – wird gesetzt…"
  printf "SESSION_SECRET=%s\n" "$(openssl rand -hex 24)" >> /opt/seller-control/.env
else
  echo "🔐 SESSION_SECRET vorhanden."
fi

# 7) Commit & Push (nur Code-Datei)
cd /opt/seller-control
git add backend/app/main.py || true
git commit -m "auth: fix SessionMiddleware import & install order; ensure SESSION_SECRET" || true
git push || true

# 8) Build & Deploy mit Logs
/opt/seller-control/update.sh -l
