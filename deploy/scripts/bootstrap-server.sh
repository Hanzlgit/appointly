#!/usr/bin/env bash
# One-time server bootstrap for Appointly production deployment.
# Run on your Linux server as a user with sudo access.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/appointly}"
REPO="${REPO:-git@github.com:Hanzlgit/appointly.git}"

echo "==> Installing Docker (skip if already installed)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  echo "Log out and back in so Docker group membership applies, then re-run this script."
  exit 0
fi

echo "==> Creating app directory"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Cloning repository"
  git clone "$REPO" "$APP_DIR"
else
  echo "==> Repository already exists at $APP_DIR"
fi

cd "$APP_DIR/deploy"

if [ ! -f .env ]; then
  echo "==> Creating .env from example — EDIT THIS FILE BEFORE STARTING"
  cp .env.example .env
  echo "Created $APP_DIR/deploy/.env — set strong passwords and DJANGO_SECRET_KEY"
fi

echo "==> Logging in to GHCR (use a GitHub PAT with read:packages)"
echo "Run manually: echo YOUR_PAT | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin"

echo ""
echo "Bootstrap complete. Next steps:"
echo "  1. Edit $APP_DIR/deploy/.env"
echo "  2. docker login ghcr.io"
echo "  3. cd $APP_DIR/deploy && docker compose -f docker-compose.prod.yml up -d"
echo "  4. Configure GitHub Secrets: DEPLOY_HOST, DEPLOY_USER, DEPLOY_SSH_KEY"
