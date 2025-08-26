#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/seller-control"
KEY_PATH="/root/.ssh/sc_mirror"

cd "$APP_DIR"

# 1) Git-Identität setzen (ggf. anpassen)
git config --global user.name  "Mahling"
git config --global user.email "kmahling@googlemail.com"

# 2) Origin sicher auf SSH setzen (nutzt deinen Deploy-Key)
if ! git remote -v | grep -q 'github.com.*Mahling/seller-control-mirror\.git'; then
  git remote remove origin 2>/dev/null || true
  # Falls du ~/.ssh/config mit "github-sc-mirror" hast, nimm die erste Zeile:
  git remote add origin git@github.com:Mahling/seller-control-mirror.git
fi

# 3) Eingebettetes Repo flatten (statt Submodule)
if [ -d repo/.git ]; then
  echo "⚠️  Gefunden: eingebettetes Git-Repo in repo/.git – entferne internes .git & reindizierte Dateien"
  rm -rf repo/.git
  git rm --cached -r repo || true
fi

# 4) .gitignore absichern (Secrets & Müll raus halten)
grep -q '^\.env$' .gitignore 2>/dev/null || cat >> .gitignore <<'GI'
.env
*.env
__pycache__/
*.pyc
venv/
.venv/
.DS_Store
GI

# 5) Commit & Push
git add -A
git commit -m "Sync from droplet (flatten nested repo & set identity)" || echo "ℹ️  Nichts zu committen."
GIT_SSH_COMMAND="ssh -o IdentitiesOnly=yes -i ${KEY_PATH}" git push -u origin main

echo "✅ Fertig. Prüfe jetzt: https://github.com/Mahling/seller-control-mirror"
