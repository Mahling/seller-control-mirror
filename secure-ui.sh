#!/usr/bin/env bash
set -euo pipefail
cd /opt/seller-control

read -rp "Admin-User (z.B. admin): " UIUSER
read -srp "Passwort: " UIPASS; echo

# Bcrypt-Hash mit Caddy erzeugen (im Container)
HASH=$(docker compose exec -T caddy caddy hash-password --plaintext "$UIPASS" | tr -d '\r')

# Caddyfile patchen: basicauth im ersten Site-Block einfügen (falls nicht schon vorhanden)
if ! grep -q "basicauth" Caddyfile; then
  awk 'BEGIN{ins=0}
       /^{/ && ins==0 {print; print "    basicauth /* {";
                       print "        '"$UIUSER"' '"$HASH"'";
                       print "    }"; ins=1; next}
       {print}' Caddyfile > Caddyfile.new
  mv Caddyfile.new Caddyfile
  echo "✅ Caddyfile: basicauth eingetragen."
else
  echo "ℹ️  Caddyfile enthält bereits basicauth – übersprungen."
fi

# Versionieren & deployen & Logs
git add Caddyfile
git commit -m "chore: add basic auth via Caddy"
git push origin main

# Caddy neu laden
docker compose restart caddy
# API-Logs mitschauen
docker compose logs -f api
