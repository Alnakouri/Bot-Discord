#!/usr/bin/env bash
set -euo pipefail
# 1. Docker Engine + plugin compose (dépôt officiel)
if ! command -v docker >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true

# 2. Dossiers runtime + perms pour l'UID non-root du conteneur (10001).
#    PIÈGE LINUX : contrairement à Docker Desktop Windows, le bind-mount garde
#    l'UID hôte. botuser (10001) doit pouvoir écrire dans data/ et logs/.
mkdir -p data logs
sudo chown -R 10001:10001 data logs
echo "✅ setup terminé. Déconnecte/reconnecte la session SSH pour activer le groupe docker."
