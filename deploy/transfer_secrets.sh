#!/usr/bin/env bash
set -euo pipefail
# Usage: ./deploy/transfer_secrets.sh <user@ip> <chemin_repo_distant>
REMOTE="${1:?user@ip requis}"; DEST="${2:?chemin repo distant requis}"
for bot in Sheogorath MaiqBot Alfred JohnnyBot OnizukaBot MalenaBot; do
  scp "./$bot/.master_key" "$REMOTE:$DEST/$bot/.master_key"
done
# Mot de passe du dashboard (créé en local au préalable, voir B.4)
scp "./dashboard/.env" "$REMOTE:$DEST/dashboard/.env"
echo "✅ Secrets transférés. Vérifie les permissions (chmod 600) côté serveur."
