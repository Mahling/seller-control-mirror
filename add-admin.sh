#!/usr/bin/env bash
set -euo pipefail
cd /opt/seller-control

read -rp "E-Mail: " EMAIL
read -rp "Benutzername: " USERNAME
read -srp "Passwort: " PASS; echo

docker compose exec -T api python - <<PY
from sqlalchemy.orm import Session
from sqlalchemy import text
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
