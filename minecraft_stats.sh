#!/bin/bash
# Runner for Minecraft stats sync on Ubuntu
set -e

SCRIPT_DIR="/home/ipl/PythonScripts/minecraft_stats"
LOG_FILE="/home/ipl/mcstats-sync.log"

echo "=== Minecraft Stats Sync ===" | tee -a "$LOG_FILE"
echo "Started: $(date)" | tee -a "$LOG_FILE"

if [ ! -d "$SCRIPT_DIR" ]; then
    echo "ERROR: Script directory not found: $SCRIPT_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

cd "$SCRIPT_DIR" || exit 1
echo "Working directory: $(pwd)" | tee -a "$LOG_FILE"

if [ ! -d ".venv" ]; then
    echo "ERROR: Virtual environment not found. Run ./install.sh first" | tee -a "$LOG_FILE"
    exit 1
fi

echo "Activating virtual environment..." | tee -a "$LOG_FILE"
source .venv/bin/activate

echo "Running sync_stats.py..." | tee -a "$LOG_FILE"
python sync_stats.py 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}
if [ $EXIT_CODE -eq 0 ]; then
    echo "Completed successfully: $(date)" | tee -a "$LOG_FILE"
else
    echo "ERROR: Script failed with exit code $EXIT_CODE at $(date)" | tee -a "$LOG_FILE"
fi

echo "===========================" | tee -a "$LOG_FILE"
echo ""

exit $EXIT_CODE