#!/usr/bin/env bash
set -euo pipefail

cd /opt/seller-control

# 1) Git vorbereiten (Identität setzen, falls noch nicht vorhanden)
git config user.email >/dev/null 2>&1 || git config user.email "root@$(hostname -f 2>/dev/null || hostname)"
git config user.name  >/dev/null 2>&1 || git config user.name  "DO Droplet"

# Sicherstellen, dass ein Repo vorhanden ist (falls Ordner leer angelegt wurde)
if [ ! -d .git ]; then
  git clone https://github.com/Mahling/seller-control-mirror.git .
fi

# Auf main und aktuell ziehen (rebase erhält lokale Änderungen sauber)
git checkout -B main
git pull --rebase origin main || true

# 2) Änderungen committen & pushen
git add -A
if git diff --cached --quiet; then
  echo "ℹ️  Keine lokalen Änderungen zu committen."
else
  git commit -m "deploy: $(date -u +'%Y-%m-%d %H:%M:%S') UTC"
fi

if ! git push origin main; then
  echo "❌ Push fehlgeschlagen. Prüfe die Remote-URL/Credentials (HTTPS mit Token oder SSH-Key)."
  exit 1
fi

# 3) Build & Start (mit Cache, ohne No-Cache-Zwang)
docker compose up -d --build --remove-orphans

# Optional: DB-Migration, wenn Alembic vorhanden ist (fehler-tolerant)
if docker compose exec -T api sh -lc 'command -v alembic >/dev/null 2>&1'; then
  docker compose exec -T api alembic upgrade head || true
fi

# Logs followen (blockiert bewusst, bis STRG+C)
exec docker compose logs -f
