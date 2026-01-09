#!/bin/bash
set -euo pipefail

# First-install helper for Minecraft Stats sync on Ubuntu
# - Creates/updates virtual env
# - Installs requirements
# - Leaves venv ready for running sync_stats.py

# Change to script directory
cd "$(dirname "$0")"

PYTHON_BIN="python3"
VENV_DIR=".venv"
REQ_FILE="requirements.txt"

# Ensure python3-venv exists (Debian/Ubuntu)
if ! command -v $PYTHON_BIN >/dev/null 2>&1; then
  echo "python3 not found. Please install Python 3." >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[install] Creating venv in $VENV_DIR"
  $PYTHON_BIN -m venv "$VENV_DIR"
else
  echo "[install] Using existing venv $VENV_DIR"
fi

# Activate venv
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip

# Install requirements
if [ -f "$REQ_FILE" ]; then
  pip install -r "$REQ_FILE"
else
  echo "[install] requirements.txt not found; skipping"
fi

echo "[install] Done. Activate with: source $VENV_DIR/bin/activate"
