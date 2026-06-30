#!/bin/bash
# Setup all OzzyBot cron jobs
# Run once after cloning/setup

set -e

OZ_DIR="/home/rick/ozzy-bot"

echo "Setting up OzzyBot cron jobs..."

# Build crontab
cat > /tmp/ozzybot_cron << EOF
# OzzyBot cron jobs
SHELL=/bin/bash
PATH=/home/rick/.local/bin:/usr/local/bin:/usr/bin:/bin
XDG_RUNTIME_DIR=/run/user/1000

# Signal generator — hourly at :05
5 * * * * cd $OZ_DIR && source venv/bin/activate && python3 signal_generator.py >> $OZ_DIR/logs/signal_generator.log 2>&1

# Health check — every 5 minutes
*/5 * * * * cd $OZ_DIR && bash scripts/health_check.sh >> $OZ_DIR/logs/health_check.log 2>&1

# Daily testnet analysis — 7:00 AM
0 7 * * * cd $OZ_DIR && source venv/bin/activate && python3 scripts/analyze_last_24h.py >> $OZ_DIR/logs/daily_analysis.log 2>&1

# Weekly review — Sunday 6:00 PM
0 18 * * 0 cd $OZ_DIR && source venv/bin/activate && python3 scripts/weekly_review.py >> $OZ_DIR/logs/weekly_review.log 2>&1

# Daily backup to Google Drive — 3:00 AM
0 3 * * * cd $OZ_DIR && bash scripts/backup_to_gdrive.sh >> $OZ_DIR/logs/backup.log 2>&1

# Local backup — 2:00 AM
0 2 * * * cd $OZ_DIR && bash scripts/backup.sh >> $OZ_DIR/logs/backup.log 2>&1
EOF

# Install
crontab /tmp/ozzybot_cron
rm /tmp/ozzybot_cron

echo "✅ Cron jobs installed!"
echo ""
crontab -l | grep -v "^#" | grep -v "^$"
echo ""
echo "To edit manually: crontab -e"
