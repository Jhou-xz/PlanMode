#!/bin/bash
set -e

# Run as root on Ubuntu 24.04
apt-get update
apt-get install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib ffmpeg tesseract-ocr

# Create database user and database
sudo -u postgres psql -c "CREATE USER planmode WITH PASSWORD 'change_me';" || true
sudo -u postgres psql -c "CREATE DATABASE planmode OWNER planmode;" || true

# Create app user and directory
useradd -r -s /bin/false planmode || true
mkdir -p /opt/plan-mode
chown planmode:planmode /opt/plan-mode

# App code and venv are expected to be copied/installed by deploy script
cd /opt/plan-mode
python3.12 -m venv .venv
.venv/bin/pip install -e "."

# Copy service file and start
cp deploy/plan-mode.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable plan-mode.service
systemctl start plan-mode.service
