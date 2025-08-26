#!/usr/bin/env bash
set -euo pipefail

cd /opt/seller-control

read -p "E-Mail: " EMAIL
read -p "Benutzername: " USERNAME
read -s -p "Passwort: " PASS
echo

# sicherstellen, dass die Container laufen (ohne Neu-Build)
if ! docker compose ps api --format '{{.State}}' | grep -qi running; then
  echo "ℹ️  Starte api & db ..."
  docker compose up -d db api
fi

# wenn api läuft: exec, sonst (Fallback) run
if docker compose ps api --format '{{.State}}' | grep -qi running; then
  RUNNER="exec -T"
else
  RUNNER="run --rm -T"
fi

# Benutzer anlegen
docker compose $RUNNER api python - <<PY
from sqlalchemy.orm import Session
from app.auth import ensure_users_table, create_user
from app.db import SessionLocal  # <- richtiger Import

db: Session = SessionLocal()
try:
    ensure_users_table(db)
    uid = create_user(db, "${EMAIL}", "${USERNAME}", "${PASS}")
    print("✅ Benutzer angelegt, ID =", uid)
finally:
    db.close()
PY
