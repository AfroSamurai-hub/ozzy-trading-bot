#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="/home/rick/ozzy-simple"
PY="$REPO_DIR/venv/bin/python"
SCRIPT="$REPO_DIR/scripts/generate_project_report.py"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting PROJECT_REPORT generation" | tee -a "$LOG_DIR/report_cron.log"
"$PY" "$SCRIPT" 2>&1 | tee -a "$LOG_DIR/report_cron.log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed" | tee -a "$LOG_DIR/report_cron.log"