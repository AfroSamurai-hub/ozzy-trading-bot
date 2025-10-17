# 📸 OZZY SNAPSHOT & BACKUP SYSTEM

## 🎯 Quick Overview

Your entire OZZY system can be saved and restored at any time. This includes:
- ✅ All code (agent, strategies, utilities)
- ✅ Pattern database (2,494+ labeled patterns)
- ✅ Trade history and portfolio state
- ✅ Configuration and settings
- ✅ Logs and monitoring data
- ✅ Documentation and analysis

---

## 🚀 QUICK COMMANDS

### Create a Snapshot
```bash
cd /home/rick/ozzy-simple
./scripts/create_snapshot.sh
```

### List All Snapshots
```bash
ls -lh snapshots/*.tar.gz
```

### View Snapshot History
```bash
cat snapshots/snapshot_history.log
```

### Restore Latest Snapshot
```bash
# Find latest
LATEST=$(ls -t snapshots/snapshot_*.tar.gz | head -1)

# Extract
tar -xzf "$LATEST" -C snapshots/

# Get snapshot name
SNAPSHOT_DIR=$(basename "$LATEST" .tar.gz)

# Restore (CAREFUL - overwrites current files!)
rsync -av snapshots/$SNAPSHOT_DIR/code/ /home/rick/ozzy-simple/
cp -r snapshots/$SNAPSHOT_DIR/data/* /home/rick/ozzy-simple/data/
```

---

## 📦 WHAT'S INCLUDED IN EACH SNAPSHOT

### 1. **Code** (63MB)
- `agent/` - AI trading agent
- `intelligence/` - Pattern intelligence & learning
- `stream/` - Market data streaming
- `scripts/` - Utility scripts
- `dashboard/` - Monitoring dashboards
- All Python modules and utilities

### 2. **Data** (10MB)
- **Pattern Database**: ChromaDB vector store with all labeled patterns
- **Trade History**: Complete CSV of all trades
- **Portfolio State**: Current positions and capital
- **Positions**: Open trades with TP/SL

### 3. **Configuration** (20KB)
- `.env` (sanitized - API keys redacted for security)
- `config/` directory
- `requirements.txt` - Python dependencies
- System configurations

### 4. **Logs** (22MB)
- System logs (last 7 days)
- Test outputs
- Decision logs
- Error logs
- Performance logs

### 5. **Documentation** (1.1MB)
- Architecture docs
- User guides
- Test reports
- Bug history
- Analysis documents

### 6. **Monitoring** (108KB)
- Live test monitoring sheets
- Running process states
- Git status and commits
- System information

---

## 🔄 RESTORATION SCENARIOS

### Scenario 1: Full System Restore
**Use case:** System crashed, need to recover everything
```bash
cd /home/rick/ozzy-simple
SNAPSHOT="snapshot_20251017_072924"  # Your snapshot name

# Extract
tar -xzf snapshots/${SNAPSHOT}.tar.gz -C snapshots/

# Restore everything
rsync -av snapshots/${SNAPSHOT}/code/ ./
cp -r snapshots/${SNAPSHOT}/data/* ./data/
cp -r snapshots/${SNAPSHOT}/config/* ./config/

# Recreate venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Restore .env (add your API keys!)
cp snapshots/${SNAPSHOT}/config/.env.sanitized .env
# EDIT .env and add your actual API keys

echo "✅ Full system restored!"
```

### Scenario 2: Restore Pattern Database Only
**Use case:** Corrupted patterns, need to restore knowledge base
```bash
SNAPSHOT="snapshot_20251017_072924"

# Extract if needed
tar -xzf snapshots/${SNAPSHOT}.tar.gz -C snapshots/

# Restore patterns
rm -rf data/vector_db
cp -r snapshots/${SNAPSHOT}/data/vector_db data/

echo "✅ Pattern database restored!"
```

### Scenario 3: Restore Trade History
**Use case:** Lost trades.csv, need historical data
```bash
SNAPSHOT="snapshot_20251017_072924"
tar -xzf snapshots/${SNAPSHOT}.tar.gz -C snapshots/
cp snapshots/${SNAPSHOT}/data/trades.csv ./

echo "✅ Trade history restored!"
```

### Scenario 4: Compare Code Changes
**Use case:** Want to see what changed since snapshot
```bash
SNAPSHOT="snapshot_20251017_072924"
tar -xzf snapshots/${SNAPSHOT}.tar.gz -C snapshots/

# Compare files
diff -r snapshots/${SNAPSHOT}/code/agent/trader.py agent/trader.py

# Or use meld for visual diff
meld snapshots/${SNAPSHOT}/code/agent/ agent/
```

### Scenario 5: Restore Specific File
**Use case:** Broke a specific file, need working version
```bash
SNAPSHOT="snapshot_20251017_072924"
tar -xzf snapshots/${SNAPSHOT}.tar.gz -C snapshots/

# Restore single file
cp snapshots/${SNAPSHOT}/code/agent/trader.py agent/trader.py

echo "✅ File restored!"
```

---

## 🔐 BACKUP STRATEGIES

### Strategy 1: Automated Daily Snapshots
```bash
# Add to crontab (crontab -e)
0 2 * * * cd /home/rick/ozzy-simple && ./scripts/create_snapshot.sh >> logs/snapshot.log 2>&1

# This runs every day at 2 AM
```

### Strategy 2: Pre-Major-Change Snapshot
```bash
# Before implementing fixes or major updates
./scripts/create_snapshot.sh

# Make your changes
# If something breaks, restore from snapshot
```

### Strategy 3: External Backup
```bash
# Copy to external drive
cp snapshots/snapshot_*.tar.gz /media/external-drive/ozzy-backups/

# Or upload to cloud
rclone copy snapshots/snapshot_*.tar.gz dropbox:ozzy-backups/

# Or use rsync to remote server
rsync -av snapshots/ user@backup-server:/backups/ozzy/
```

### Strategy 4: Git-Based Versioning
```bash
# Commit current state to git
git add -A
git commit -m "Snapshot: $(date)"
git tag -a snapshot-$(date +%Y%m%d) -m "System snapshot"

# Push to GitHub (private repo recommended!)
git push origin main --tags
```

---

## 📊 SNAPSHOT MANAGEMENT

### Clean Old Snapshots
```bash
# Keep only last 10 snapshots
cd /home/rick/ozzy-simple/snapshots
ls -t snapshot_*.tar.gz | tail -n +11 | xargs rm -f

echo "✅ Old snapshots cleaned"
```

### View Snapshot Details
```bash
SNAPSHOT="snapshot_20251017_072924"
tar -xzf snapshots/${SNAPSHOT}.tar.gz -C snapshots/

# Read manifest
cat snapshots/${SNAPSHOT}/MANIFEST.md | less

# See file tree
tree -L 2 snapshots/${SNAPSHOT}/
```

### Compare Two Snapshots
```bash
SNAPSHOT1="snapshot_20251017_072924"
SNAPSHOT2="snapshot_20251017_080000"

# Extract both
tar -xzf snapshots/${SNAPSHOT1}.tar.gz -C snapshots/
tar -xzf snapshots/${SNAPSHOT2}.tar.gz -C snapshots/

# Compare
diff -r snapshots/${SNAPSHOT1}/ snapshots/${SNAPSHOT2}/
```

---

## ⚠️ IMPORTANT NOTES

### Security
- ✅ **API Keys Redacted**: Snapshots don't contain real API keys
- ✅ **Sanitized Config**: .env files are cleaned before saving
- ⚠️ **Strategy Data**: Patterns and trades ARE included (contains your edge!)
- 🔒 **Store Securely**: Keep snapshots private if using real trading data

### What's NOT Included
- ❌ **Virtual Environment** (`venv/`) - Too large (60MB+), recreate from requirements.txt
- ❌ **Full Git History** (`.git/`) - Only recent commits captured
- ❌ **Archive Folder** - Old code not included
- ❌ **Cache Files** (`__pycache__/`, `.pytest_cache/`)

### Restoration Tips
1. **Always check MANIFEST.md** - Know what you're restoring
2. **Backup current state first** - Before restoring, snapshot current state
3. **Test in staging** - If possible, restore to a test environment first
4. **Verify integrity** - Check tar archives: `tar -tzf snapshot.tar.gz`
5. **Review git diff** - After restore, check what changed: `git diff`

---

## 🚨 EMERGENCY RECOVERY

### System Completely Broken
```bash
# 1. Find most recent working snapshot
ls -lt snapshots/*.tar.gz | head -5

# 2. Extract
tar -xzf snapshots/snapshot_YYYYMMDD_HHMMSS.tar.gz -C /tmp/

# 3. Restore from /tmp (safer than direct overwrite)
cd /home/rick/ozzy-simple
rsync -av /tmp/snapshot_YYYYMMDD_HHMMSS/code/ ./

# 4. Verify
python -m pytest tests/ -v

# 5. If tests pass, restore data
cp -r /tmp/snapshot_YYYYMMDD_HHMMSS/data/* ./data/
```

### Pattern Database Corrupted
```bash
# Quick recovery
SNAPSHOT=$(ls -t snapshots/snapshot_*.tar.gz | head -1)
tar -xzOf "$SNAPSHOT" snapshot_*/data/vector_db | tar -xzf - -C data/

# Verify
python -c "from intelligence.pattern_library import check_pattern_health; check_pattern_health()"
```

### Lost All Configuration
```bash
SNAPSHOT=$(ls -t snapshots/snapshot_*.tar.gz | head -1)
tar -xzOf "$SNAPSHOT" snapshot_*/config/requirements.txt > requirements.txt

# Recreate environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Get config template
tar -xzOf "$SNAPSHOT" snapshot_*/config/.env.sanitized > .env
echo "⚠️ Edit .env and add your API keys!"
```

---

## 📈 MONITORING SNAPSHOT HEALTH

### Check Snapshot Integrity
```bash
# Verify tar archive
tar -tzf snapshots/snapshot_20251017_072924.tar.gz > /dev/null && echo "✅ Archive OK" || echo "❌ Archive corrupted"

# Check manifest exists
tar -xzOf snapshots/snapshot_20251017_072924.tar.gz snapshot_*/MANIFEST.md > /dev/null && echo "✅ Manifest OK"
```

### Snapshot Size Trends
```bash
# Track snapshot sizes over time
ls -lh snapshots/*.tar.gz | awk '{print $9, $5}' | sort
```

### Verify Snapshot Contents
```bash
# List all files in snapshot
tar -tzf snapshots/snapshot_20251017_072924.tar.gz | less

# Count files by type
tar -tzf snapshots/snapshot_20251017_072924.tar.gz | grep -E '\.(py|json|csv|md)$' | wc -l
```

---

## 🎯 BEST PRACTICES

1. **Snapshot Before Major Changes**
   - Before implementing fixes
   - Before upgrading dependencies
   - Before restructuring code

2. **Regular Automated Snapshots**
   - Daily at off-peak hours
   - Before each trading session
   - After completing major features

3. **Test Restoration Periodically**
   - Monthly restore drills
   - Verify snapshots aren't corrupted
   - Practice recovery procedures

4. **Maintain Snapshot History**
   - Keep at least 7 daily snapshots
   - Keep weekly snapshots for 1 month
   - Keep monthly snapshots for 1 year

5. **Off-site Backup**
   - Copy to external drive weekly
   - Upload to cloud storage
   - Keep at different physical location

6. **Document Important Snapshots**
   ```bash
   # Tag important snapshots
   mv snapshots/snapshot_20251017_072924.tar.gz \
      snapshots/IMPORTANT_PreFix_snapshot_20251017_072924.tar.gz
   ```

---

## 💡 QUICK REFERENCE

```bash
# Create snapshot
./scripts/create_snapshot.sh

# List snapshots
ls -lh snapshots/*.tar.gz

# Extract specific snapshot
tar -xzf snapshots/snapshot_YYYYMMDD_HHMMSS.tar.gz -C snapshots/

# Restore full system
rsync -av snapshots/snapshot_YYYYMMDD_HHMMSS/code/ ./
cp -r snapshots/snapshot_YYYYMMDD_HHMMSS/data/* ./data/

# Restore single file
cp snapshots/snapshot_YYYYMMDD_HHMMSS/code/path/to/file.py path/to/file.py

# Compare with current
diff -r snapshots/snapshot_YYYYMMDD_HHMMSS/code/agent/ agent/

# Clean old snapshots (keep 10)
ls -t snapshots/snapshot_*.tar.gz | tail -n +11 | xargs rm -f

# View snapshot manifest
tar -xzOf snapshots/snapshot_*.tar.gz snapshot_*/MANIFEST.md | less
```

---

## 📞 SUPPORT

If you have issues with snapshots:
1. Check `snapshots/snapshot_history.log` for snapshot creation history
2. Verify tar archive integrity: `tar -tzf snapshot.tar.gz > /dev/null`
3. Read MANIFEST.md in the snapshot for detailed contents
4. Check available disk space: `df -h`

---

**Created:** October 17, 2025
**Version:** 1.0
**Snapshot System:** Fully operational ✅

Your system is protected! 🛡️
