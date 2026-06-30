#!/bin/bash
# ==============================================================================
# OzzyBot Log Rotation / Truncation
# Checks all main log files and keeps only the last 10,000 lines if they exceed 5MB.
# Uses safe in-place truncation to preserve open file descriptors.
# ==============================================================================

REPO_ROOT="/home/rick/ozzy-bot"
MAX_LINES=10000
MAX_SIZE_MB=5

log_files=(
    "$REPO_ROOT/trades.log"
    "$REPO_ROOT/breakeven_monitor.log"
    "$REPO_ROOT/health_check.log"
    "$REPO_ROOT/logs/signal_generator.log"
    "$REPO_ROOT/logs/watchdog.log"
    "$REPO_ROOT/logs/backup.log"
)

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] Starting OzzyBot log rotation check..."

for log in "${log_files[@]}"; do
    if [ ! -f "$log" ]; then
        continue
    fi

    # Check file size in MB
    size_mb=$(du -m "$log" | cut -f1)

    if [ "$size_mb" -ge "$MAX_SIZE_MB" ]; then
        echo "[$(ts)] 🔄 Truncating $log in-place (Current size: ${size_mb}MB >= ${MAX_SIZE_MB}MB)..."
        
        tmp_file="${log}.tmp"
        
        # Keep only the last MAX_LINES
        if tail -n "$MAX_LINES" "$log" > "$tmp_file"; then
            # In-place truncation preserves inode and active file descriptors
            if cat "$tmp_file" > "$log"; then
                rm -f "$tmp_file"
                new_size=$(du -h "$log" | cut -f1)
                echo "[$(ts)] ✅ Truncated $log successfully. New size: $new_size."
            else
                echo "[$(ts)] ❌ Failed to write back to $log!"
                rm -f "$tmp_file"
            fi
        else
            echo "[$(ts)] ❌ Failed to extract tail of $log!"
            rm -f "$tmp_file"
        fi
    fi
done

echo "[$(ts)] Log rotation check complete."
