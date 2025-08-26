#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Mahling/seller-control-mirror.git"
APP_DIR="/opt/seller-control"

cd "$APP_DIR"

# Git sauber aktualisieren
if [ ! -d .git ]; then
  git init
  git remote add origin "$REPO_URL" || true
fi
git fetch --prune origin main
git reset --hard origin/main

# .env muss vorhanden sein
if [ ! -f .env ]; then
  cat <<'EOT'
❌ .env fehlt unter /opt/seller-control
Lege sie an, z. B.:
LWA_CLIENT_ID=amzn1.application-oa2-client.XXXX
LWA_CLIENT_SECRET=amzn1.oa2-cs.v1.XXXX
NO_AWS_MODE=1
SP_REGION=eu
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/postgres
EOT
  exit 1
fi

# docker compose wrapper (unterstützt "docker compose" und "docker-compose")
dcompose() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

# Images ziehen/neu bauen & starten
dcompose pull || true
dcompose up -d --build --remove-orphans

# DB-Migration (nicht fatal, wenn Alembic nicht konfiguriert)
dcompose exec -T api alembic upgrade head || true

# Aufräumen
docker image prune -f || true

echo "✅ Update/Deploy fertig."
