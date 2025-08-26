#!/usr/bin/env bash
set -euo pipefail
cd /opt/seller-control

EMAIL="${1:-}"; USERNAME="${2:-}"; PASS="${3:-}"
[ -n "$EMAIL" ]    || read -rp "E-Mail: " EMAIL
[ -n "$USERNAME" ] || read -rp "Benutzername: " USERNAME
if [ -z "${PASS}" ]; then read -srp "Passwort: " PASS; echo; fi

# Ermitteln, ob der api-Container läuft
CID="$(docker compose ps -q api || true)"
RUNNER="exec -T"
if [ -z "$CID" ] || [ "$(docker inspect -f '{{.State.Running}}' "$CID" 2>/dev/null || echo false)" != "true" ]; then
  RUNNER="run --rm -T"
fi

docker compose $RUNNER api python - <<PY
from sqlalchemy.orm import Session
from app.auth import ensure_users_table, create_user
from app.database import SessionLocal
db: Session = SessionLocal()
try:
    ensure_users_table(db)
    uid = create_user(db, "${EMAIL}", "${USERNAME}", "${PASS}")
    print("✅ Benutzer angelegt, ID =", uid)
finally:
    db.close()
PY
