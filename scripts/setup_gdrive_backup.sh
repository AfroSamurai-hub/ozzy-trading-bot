#!/bin/bash
# Setup Google Drive backup for OzzyBot
# Run once to configure, then backups happen automatically via cron

set -e

RCLONE="$HOME/.local/bin/rclone"
CONFIG_DIR="$HOME/.config/rclone"
OZ_DIR="/home/rick/ozzy-bot"

# Check if rclone exists
if [ ! -f "$RCLONE" ]; then
    echo "Installing rclone..."
    mkdir -p "$HOME/.local/bin"
    cd /tmp
    curl -s -O https://downloads.rclone.org/rclone-current-linux-amd64.zip
    unzip -o rclone-current-linux-amd64.zip
    cp rclone-*-linux-amd64/rclone "$RCLONE"
    chmod +x "$RCLONE"
    echo "rclone installed to $RCLONE"
fi

# Add to PATH if needed
if ! command -v rclone &> /dev/null; then
    export PATH="$HOME/.local/bin:$PATH"
    if ! grep -q "$HOME/.local/bin" "$HOME/.bashrc" 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        echo "Added ~/.local/bin to PATH in .bashrc"
    fi
fi

mkdir -p "$CONFIG_DIR"

echo ""
echo "========================================"
echo "  OzzyBot Google Drive Backup Setup"
echo "========================================"
echo ""
echo "This will configure rclone to backup your bot data to Google Drive."
echo ""
echo "Step 1: Create a Google Drive folder for backups"
echo "  - Go to https://drive.google.com"
echo "  - Create a folder called 'OzzyBot-Backups'"
echo "  - Note the folder name exactly (case-sensitive)"
echo ""
echo "Step 2: Run rclone config (follow the interactive prompts)"
echo "  - Choose 'n' for new remote"
echo "  - Name it: ozzybot-gdrive"
echo "  - Choose '18' for Google Drive (or find the number for 'drive')"
echo "  - Leave client_id and client_secret blank (default)"
echo "  - Choose '1' for full access"
echo "  - Say 'n' to edit advanced config"
echo "  - Say 'y' to auto config (opens browser)"
echo "  - Log in with your Google account and allow access"
echo "  - Say 'y' to confirm"
echo "  - Say 'q' to quit config"
echo ""
read -p "Press ENTER when you're ready to start rclone config..."

$RCLONE config

echo ""
echo "Step 3: Testing connection..."
$RCLONE ls ozzybot-gdrive: | head -5 && echo "✅ Google Drive connected!" || echo "❌ Connection failed. Run rclone config again."

echo ""
echo "Step 4: Creating backup script..."

mkdir -p "$OZ_DIR/scripts"

cat > "$OZ_DIR/scripts/backup_to_gdrive.sh" << 'EOF'
#!/bin/bash
# OzzyBot backup to Google Drive
# Run manually or via cron

set -e

RCLONE="$HOME/.local/bin/rclone"
OZ_DIR="/home/rick/ozzy-bot"
BACKUP_NAME="ozzybot_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
LOCAL_BACKUP="$OZ_DIR/backups/$BACKUP_NAME"
GDRIVE_REMOTE="ozzybot-gdrive:OzzyBot-Backups"

mkdir -p "$OZ_DIR/backups"

echo "[$(date)] Starting backup to Google Drive..."

# Create local tar.gz
tar -czf "$LOCAL_BACKUP" \
    -C "$OZ_DIR" \
    trades.db *.log *.py *.json .env scripts/ \
    .config/systemd/user/ozzybot-*.service 2>/dev/null || true

# Also backup the docs directory
tar -czf "$OZ_DIR/backups/ozzybot_docs_$(date +%Y%m%d).tar.gz" \
    -C "$OZ_DIR" docs/ 2>/dev/null || true

# Sync to Google Drive
$RCLONE copy "$LOCAL_BACKUP" "$GDRIVE_REMOTE/"
$RCLONE copy "$OZ_DIR/backups/ozzybot_docs_$(date +%Y%m%d).tar.gz" "$GDRIVE_REMOTE/" 2>/dev/null || true

# Clean old local backups (keep last 10)
ls -t "$OZ_DIR"/backups/ozzybot_backup_*.tar.gz 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true

# Clean old Google Drive backups (keep last 30)
$RCLONE delete --min-age 30d "$GDRIVE_REMOTE/" 2>/dev/null || true

echo "[$(date)] Backup complete: $BACKUP_NAME"
echo "[$(date)] Google Drive folder: OzzyBot-Backups"
EOF

chmod +x "$OZ_DIR/scripts/backup_to_gdrive.sh"

echo "Backup script created at: $OZ_DIR/scripts/backup_to_gdrive.sh"

echo ""
echo "Step 5: Testing backup..."
bash "$OZ_DIR/scripts/backup_to_gdrive.sh"

echo ""
echo "Step 6: Add to crontab (run daily at 3 AM)..."
(crontab -l 2>/dev/null | grep -v "backup_to_gdrive" ; echo "0 3 * * * bash /home/rick/ozzy-bot/scripts/backup_to_gdrive.sh >> /home/rick/ozzy-bot/logs/backup.log 2>&1") | crontab -

echo "✅ Daily backup scheduled!"
echo ""
echo "========================================"
echo "  Backup Summary"
echo "========================================"
echo "Local backups:  $OZ_DIR/backups/"
echo "Google Drive:   OzzyBot-Backups/"
echo "Schedule:       Daily at 3:00 AM"
echo "Retention:      10 local, 30 days on Drive"
echo ""
echo "Manual backup:  bash $OZ_DIR/scripts/backup_to_gdrive.sh"
echo ""
