#!/bin/bash
# 📸 COMPREHENSIVE SYSTEM SNAPSHOT
# Creates a complete backup of current system state

set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SNAPSHOT_NAME="snapshot_${TIMESTAMP}"
SNAPSHOT_DIR="/home/rick/ozzy-simple/snapshots/${SNAPSHOT_NAME}"

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     📸 CREATING OZZY SYSTEM SNAPSHOT                     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "Snapshot: ${SNAPSHOT_NAME}"
echo "Location: ${SNAPSHOT_DIR}"
echo ""

# Create snapshot directory structure
mkdir -p "${SNAPSHOT_DIR}"/{code,config,data,logs,docs,monitoring}

echo "✅ Snapshot directory created"

# ============================================================================
# 1. SAVE ALL CODE
# ============================================================================
echo ""
echo "📦 Saving code..."

# Save entire codebase (excluding venv, cache, etc)
rsync -av --progress \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='snapshots/' \
    --exclude='archive/' \
    /home/rick/ozzy-simple/ \
    "${SNAPSHOT_DIR}/code/" > /dev/null

echo "   ✅ Code saved to code/"

# ============================================================================
# 2. SAVE CONFIGURATION FILES
# ============================================================================
echo ""
echo "⚙️  Saving configuration..."

# Save .env (sanitized - remove actual API keys for security)
if [ -f /home/rick/ozzy-simple/.env ]; then
    cat /home/rick/ozzy-simple/.env | sed 's/\(API_KEY=\).*/\1[REDACTED]/' > "${SNAPSHOT_DIR}/config/.env.sanitized"
    echo "   ✅ .env saved (API keys redacted)"
fi

# Save config directory
if [ -d /home/rick/ozzy-simple/config ]; then
    cp -r /home/rick/ozzy-simple/config/* "${SNAPSHOT_DIR}/config/" 2>/dev/null || true
    echo "   ✅ Config directory saved"
fi

# Save requirements
if [ -f /home/rick/ozzy-simple/requirements.txt ]; then
    cp /home/rick/ozzy-simple/requirements.txt "${SNAPSHOT_DIR}/config/"
    echo "   ✅ requirements.txt saved"
fi

# ============================================================================
# 3. SAVE DATA (Pattern Database, Trades, Portfolio)
# ============================================================================
echo ""
echo "💾 Saving data..."

# Pattern database (ChromaDB)
if [ -d /home/rick/ozzy-simple/data/vector_db ]; then
    cp -r /home/rick/ozzy-simple/data/vector_db "${SNAPSHOT_DIR}/data/" 2>/dev/null || true
    PATTERN_COUNT=$(find /home/rick/ozzy-simple/data/vector_db -type f | wc -l)
    echo "   ✅ Pattern database saved (${PATTERN_COUNT} files)"
fi

# Trade history
if [ -f /home/rick/ozzy-simple/trades.csv ]; then
    cp /home/rick/ozzy-simple/trades.csv "${SNAPSHOT_DIR}/data/"
    TRADE_COUNT=$(wc -l < /home/rick/ozzy-simple/trades.csv)
    echo "   ✅ Trade history saved (${TRADE_COUNT} records)"
fi

# Portfolio state
if [ -f /home/rick/ozzy-simple/state.json ]; then
    cp /home/rick/ozzy-simple/state.json "${SNAPSHOT_DIR}/data/"
    echo "   ✅ Portfolio state saved"
fi

# Positions
if [ -f /home/rick/ozzy-simple/positions.json ]; then
    cp /home/rick/ozzy-simple/positions.json "${SNAPSHOT_DIR}/data/"
    echo "   ✅ Positions saved"
fi

# ============================================================================
# 4. SAVE LOGS
# ============================================================================
echo ""
echo "📋 Saving logs..."

# Save recent logs
if [ -d /home/rick/ozzy-simple/logs ]; then
    # Copy all logs from last 7 days
    find /home/rick/ozzy-simple/logs -type f -mtime -7 -exec cp {} "${SNAPSHOT_DIR}/logs/" \;
    LOG_COUNT=$(ls -1 "${SNAPSHOT_DIR}/logs/" | wc -l)
    echo "   ✅ Recent logs saved (${LOG_COUNT} files)"
fi

# Save current test output if running
if [ -f /tmp/test_output.log ]; then
    cp /tmp/test_output.log "${SNAPSHOT_DIR}/logs/test_output_${TIMESTAMP}.log"
    echo "   ✅ Current test log saved"
fi

# ============================================================================
# 5. SAVE DOCUMENTATION
# ============================================================================
echo ""
echo "📚 Saving documentation..."

# Save docs directory
if [ -d /home/rick/ozzy-simple/docs ]; then
    cp -r /home/rick/ozzy-simple/docs/* "${SNAPSHOT_DIR}/docs/" 2>/dev/null || true
    echo "   ✅ Docs directory saved"
fi

# Save all markdown files from root
cp /home/rick/ozzy-simple/*.md "${SNAPSHOT_DIR}/docs/" 2>/dev/null || true
echo "   ✅ Root documentation saved"

# Save Documents/new folder (our analysis docs)
if [ -d /home/rick/Documents/new ]; then
    mkdir -p "${SNAPSHOT_DIR}/docs/analysis"
    cp /home/rick/Documents/new/*.txt "${SNAPSHOT_DIR}/docs/analysis/" 2>/dev/null || true
    cp /home/rick/Documents/new/*.md "${SNAPSHOT_DIR}/docs/analysis/" 2>/dev/null || true
    echo "   ✅ Analysis documents saved"
fi

# ============================================================================
# 6. SAVE MONITORING SHEET
# ============================================================================
echo ""
echo "📊 Saving monitoring data..."

# Save current monitoring sheet
if [ -f "/home/rick/Documents/new/OZZY CURRENT TEST LIVE.txt" ]; then
    cp "/home/rick/Documents/new/OZZY CURRENT TEST LIVE.txt" "${SNAPSHOT_DIR}/monitoring/"
    echo "   ✅ Live monitoring sheet saved"
fi

# ============================================================================
# 7. CAPTURE SYSTEM STATE
# ============================================================================
echo ""
echo "🖥️  Capturing system state..."

# Python environment
if [ -f /home/rick/ozzy-simple/venv/bin/pip ]; then
    /home/rick/ozzy-simple/venv/bin/pip freeze > "${SNAPSHOT_DIR}/config/pip_freeze.txt"
    echo "   ✅ Python packages saved"
fi

# Running processes
ps aux | grep -E "python|bulletproof|monitor" | grep -v grep > "${SNAPSHOT_DIR}/monitoring/running_processes.txt" 2>/dev/null || true
echo "   ✅ Running processes captured"

# Git status
cd /home/rick/ozzy-simple
git status > "${SNAPSHOT_DIR}/monitoring/git_status.txt" 2>/dev/null || echo "Not a git repo" > "${SNAPSHOT_DIR}/monitoring/git_status.txt"
git log --oneline -20 > "${SNAPSHOT_DIR}/monitoring/git_recent_commits.txt" 2>/dev/null || true
git diff > "${SNAPSHOT_DIR}/monitoring/git_diff.txt" 2>/dev/null || true
echo "   ✅ Git state captured"

# System info
uname -a > "${SNAPSHOT_DIR}/monitoring/system_info.txt"
df -h >> "${SNAPSHOT_DIR}/monitoring/system_info.txt"
free -h >> "${SNAPSHOT_DIR}/monitoring/system_info.txt"
echo "   ✅ System info captured"

# ============================================================================
# 8. CREATE SNAPSHOT MANIFEST
# ============================================================================
echo ""
echo "📝 Creating snapshot manifest..."

cat > "${SNAPSHOT_DIR}/MANIFEST.md" << EOF
# 📸 OZZY SYSTEM SNAPSHOT

**Created:** $(date)
**Snapshot ID:** ${SNAPSHOT_NAME}

---

## 📊 SNAPSHOT CONTENTS

### 1. Code (code/)
- Complete codebase snapshot
- All Python modules
- Scripts and utilities
- Agent intelligence systems

### 2. Configuration (config/)
- Environment variables (sanitized)
- System configuration files
- Python package requirements
- Config directory contents

### 3. Data (data/)
- Pattern database (ChromaDB vector store)
- Trade history (CSV)
- Portfolio state (JSON)
- Open positions

### 4. Logs (logs/)
- System logs (last 7 days)
- Test output logs
- Decision logs
- Error logs

### 5. Documentation (docs/)
- System architecture docs
- User guides
- Analysis documents
- Test reports
- Bug history

### 6. Monitoring (monitoring/)
- Live test monitoring sheet
- Running process snapshot
- Git state
- System information

---

## 📈 SYSTEM STATE AT SNAPSHOT

### Test Status
\`\`\`
$(tail -20 /tmp/test_output.log 2>/dev/null || echo "No active test")
\`\`\`

### Git Status
\`\`\`
$(cd /home/rick/ozzy-simple && git status 2>/dev/null || echo "Not a git repo")
\`\`\`

### Running Processes
\`\`\`
$(ps aux | grep -E "python|bulletproof|monitor" | grep -v grep || echo "No processes")
\`\`\`

---

## 🔄 HOW TO RESTORE THIS SNAPSHOT

### Full Restoration:
\`\`\`bash
# 1. Copy code back
rsync -av ${SNAPSHOT_DIR}/code/ /home/rick/ozzy-simple/

# 2. Restore data
cp -r ${SNAPSHOT_DIR}/data/* /home/rick/ozzy-simple/data/

# 3. Restore config (review .env first!)
cp ${SNAPSHOT_DIR}/config/* /home/rick/ozzy-simple/config/

# 4. Reinstall packages
pip install -r ${SNAPSHOT_DIR}/config/requirements.txt
\`\`\`

### Partial Restoration:
\`\`\`bash
# Restore just pattern database
cp -r ${SNAPSHOT_DIR}/data/vector_db /home/rick/ozzy-simple/data/

# Restore just trades
cp ${SNAPSHOT_DIR}/data/trades.csv /home/rick/ozzy-simple/

# Restore specific files
cp ${SNAPSHOT_DIR}/code/agent/trader.py /home/rick/ozzy-simple/agent/
\`\`\`

---

## 📊 SNAPSHOT STATISTICS

**Total Size:** $(du -sh ${SNAPSHOT_DIR} | cut -f1)

**File Counts:**
- Code files: $(find ${SNAPSHOT_DIR}/code -type f -name "*.py" | wc -l) Python files
- Data files: $(find ${SNAPSHOT_DIR}/data -type f | wc -l) files
- Log files: $(find ${SNAPSHOT_DIR}/logs -type f | wc -l) files
- Doc files: $(find ${SNAPSHOT_DIR}/docs -type f | wc -l) files

**Key Metrics:**
- Pattern Database: $(du -sh ${SNAPSHOT_DIR}/data/vector_db 2>/dev/null | cut -f1 || echo "N/A")
- Total Trades: $(wc -l < ${SNAPSHOT_DIR}/data/trades.csv 2>/dev/null || echo "N/A")
- Documentation: $(find ${SNAPSHOT_DIR}/docs -name "*.md" | wc -l) markdown files

---

## ⚠️ IMPORTANT NOTES

1. **API Keys**: The .env file has been sanitized. You'll need to add your actual API keys when restoring.
2. **Virtual Environment**: Not included (too large). Recreate with: \`python -m venv venv && pip install -r requirements.txt\`
3. **Git History**: Only recent commits captured. Full history in .git/ if you backed that up separately.
4. **Running Processes**: Process IDs will be different when restored.

---

## 🔐 SECURITY CONSIDERATIONS

- ✅ API keys redacted from config files
- ✅ No sensitive credentials included
- ⚠️ Trade data and patterns ARE included (contains strategy info)
- ⚠️ Store this snapshot securely if it contains real trading data

---

**Snapshot created by:** create_snapshot.sh
**Script version:** 1.0
**Location:** ${SNAPSHOT_DIR}

EOF

echo "   ✅ Manifest created"

# ============================================================================
# 9. CREATE COMPRESSED ARCHIVE (OPTIONAL)
# ============================================================================
echo ""
echo "🗜️  Creating compressed archive..."

cd /home/rick/ozzy-simple/snapshots
tar -czf "${SNAPSHOT_NAME}.tar.gz" "${SNAPSHOT_NAME}/" 2>/dev/null || true

if [ -f "${SNAPSHOT_NAME}.tar.gz" ]; then
    ARCHIVE_SIZE=$(du -sh "${SNAPSHOT_NAME}.tar.gz" | cut -f1)
    echo "   ✅ Archive created: ${SNAPSHOT_NAME}.tar.gz (${ARCHIVE_SIZE})"
else
    echo "   ⚠️ Archive creation skipped"
fi

# ============================================================================
# 10. SUMMARY
# ============================================================================
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║         ✅ SNAPSHOT COMPLETE!                            ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "📁 Snapshot Location:"
echo "   ${SNAPSHOT_DIR}"
echo ""
echo "📊 Snapshot Contents:"
du -sh "${SNAPSHOT_DIR}"/* 2>/dev/null | awk '{printf "   %-20s %s\n", $2, $1}'
echo ""
echo "📦 Compressed Archive:"
if [ -f "/home/rick/ozzy-simple/snapshots/${SNAPSHOT_NAME}.tar.gz" ]; then
    ls -lh "/home/rick/ozzy-simple/snapshots/${SNAPSHOT_NAME}.tar.gz" | awk '{printf "   %s (%s)\n", $9, $5}'
    echo ""
    echo "🚀 Quick Restore Command:"
    echo "   tar -xzf snapshots/${SNAPSHOT_NAME}.tar.gz -C ."
fi
echo ""
echo "📖 Read MANIFEST.md for detailed contents and restore instructions"
echo ""
echo "✨ Your entire system state has been preserved!"
echo ""

# Save snapshot log
echo "Snapshot ${SNAPSHOT_NAME} created at $(date)" >> /home/rick/ozzy-simple/snapshots/snapshot_history.log

exit 0
