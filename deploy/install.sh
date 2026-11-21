#!/usr/bin/env bash
# Installs clipbot on a fresh Ubuntu server and sets it up to run all the time.
#
# Public repo:   curl -fsSL https://raw.githubusercontent.com/gjgil505-debug/code-phone/main/deploy/install.sh | bash
# Private repo:  export GITHUB_TOKEN=<read-only token>; then
#                curl -fsSL -H "Authorization: token $GITHUB_TOKEN" \
#                  https://raw.githubusercontent.com/gjgil505-debug/code-phone/main/deploy/install.sh | bash
set -euo pipefail

REPO="${CLIPBOT_REPO:-github.com/gjgil505-debug/code-phone.git}"
DIR="${CLIPBOT_DIR:-$HOME/clipbot}"
RUN_USER="$(id -un)"

echo "==> Installing system packages (Python, ffmpeg, git)"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip ffmpeg

echo "==> Getting clipbot"
if [ -n "${GITHUB_TOKEN:-}" ]; then URL="https://x-access-token:${GITHUB_TOKEN}@${REPO}"; else URL="https://${REPO}"; fi
case "$REPO" in /*) URL="$REPO" ;; esac  # local path (used for testing)
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  git clone "$URL" "$DIR"
fi
cd "$DIR"

echo "==> Installing clipbot (this takes a few minutes)"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install .
sudo ln -sf "$DIR/.venv/bin/clipbot" /usr/local/bin/clipbot
[ -f .env ] || { cp .env.example .env; chmod 600 .env; }
[ -f config.yaml ] || cp config.example.yaml config.yaml

echo "==> Setting it up to run all the time (restarts on crash and after reboot)"
sudo tee /etc/systemd/system/clipbot.service >/dev/null <<UNIT
[Unit]
Description=GTA 6 hype clip bot
After=network-online.target
Wants=network-online.target

[Service]
User=${RUN_USER}
WorkingDirectory=${DIR}
EnvironmentFile=${DIR}/.env
ExecStart=${DIR}/.venv/bin/clipbot run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable clipbot >/dev/null

cat <<DONE

clipbot is installed in ${DIR}.

Next, type these one at a time:
  cd ${DIR}
  clipbot setup
DONE
