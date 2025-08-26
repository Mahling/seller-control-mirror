#!/usr/bin/env bash
set -euo pipefail

FORCE=0
if [ "${1:-}" = "-f" ]; then FORCE=1; fi

cd /opt/seller-control

# Repo aktualisieren
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git fetch --prune
  git reset --hard origin/main
else
  git clone https://github.com/Mahling/seller-control-mirror.git /opt/seller-control
fi

# .env muss lokal vorhanden sein
[ -f .env ] || { echo "❌ .env fehlt unter /opt/seller-control"; exit 1; }

# Container neu bauen; bei -f ohne Cache
docker compose down || true
if [ "$FORCE" = "1" ]; then
  docker compose build --no-cache api
else
  docker compose build api
fi
docker compose up -d --remove-orphans

# Datenbank migrieren (fehler tolerieren, falls Alembic nicht konfiguriert)
docker compose exec -T api alembic upgrade head || true

# Logs anzeigen (strg+c zum Beenden)
docker compose logs -f api
