#!/bin/bash
# Database Management for Fresh Test
# Provides options to backup, mark old trades, or start fresh

set -e

DB_FILE="ozzy_simple.db"
BACKUP_FILE="ozzy_simple_backup_$(date +%Y%m%d_%H%M%S).db"

echo "=============================================="
echo "  DATABASE MANAGEMENT - Fresh Test Setup"
echo "=============================================="
echo ""

# Check if database exists
if [ ! -f "$DB_FILE" ]; then
    echo "❌ Database file not found: $DB_FILE"
    exit 1
fi

# Count current trades
TRADE_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
echo "📊 Current database: $TRADE_COUNT trades"
echo ""

PS3="Select an option: "
options=("Backup & Mark Old Trades (Recommended)" "Backup & Start Fresh" "Just Backup" "Cancel")
select opt in "${options[@]}"
do
    case $opt in
        "Backup & Mark Old Trades (Recommended)")
            echo ""
            echo "🔄 Creating backup..."
            cp "$DB_FILE" "$BACKUP_FILE"
            echo "✅ Backup created: $BACKUP_FILE"
            
            echo ""
            echo "🏷️  Marking old trades with 'BASELINE_' prefix..."
            sqlite3 "$DB_FILE" "
                UPDATE trades 
                SET entry_reason = 'BASELINE_' || COALESCE(entry_reason, 'unknown')
                WHERE entry_reason NOT LIKE 'BASELINE_%'
                OR entry_reason IS NULL;
            "
            
            MARKED=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM trades WHERE entry_reason LIKE 'BASELINE_%';")
            echo "✅ Marked $MARKED baseline trades"
            echo ""
            echo "📝 New trades will be distinguishable from baseline"
            echo "   You can still analyze all trades together or separately"
            break
            ;;
        "Backup & Start Fresh")
            echo ""
            read -p "⚠️  This will DELETE all trades. Continue? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                echo ""
                echo "🔄 Creating backup..."
                cp "$DB_FILE" "$BACKUP_FILE"
                echo "✅ Backup created: $BACKUP_FILE"
                
                echo ""
                echo "🗑️  Deleting all trades..."
                sqlite3 "$DB_FILE" "DELETE FROM trades;"
                echo "✅ Database cleared: 0 trades remaining"
                
                echo ""
                echo "💰 Resetting paper trading balance..."
                # Note: account table may not exist in all schemas
                sqlite3 "$DB_FILE" "UPDATE account SET balance = 10000.00 WHERE EXISTS (SELECT 1 FROM account);" 2>/dev/null || echo "   (No account table to reset)"
                echo "✅ Fresh start ready!"
            else
                echo "❌ Cancelled"
            fi
            break
            ;;
        "Just Backup")
            echo ""
            echo "🔄 Creating backup..."
            cp "$DB_FILE" "$BACKUP_FILE"
            echo "✅ Backup created: $BACKUP_FILE"
            echo ""
            echo "📝 No changes made to database"
            break
            ;;
        "Cancel")
            echo ""
            echo "❌ Cancelled - no changes made"
            break
            ;;
        *) echo "❌ Invalid option $REPLY";;
    esac
done

echo ""
echo "=============================================="
echo "  Next Steps:"
echo "=============================================="
echo ""
echo "1. Start your bot:"
echo "   python main.py"
echo ""
echo "2. Monitor progress daily:"
echo "   python scripts/test_tracker.py"
echo ""
echo "3. After 7 days (or 50+ trades):"
echo "   python scripts/test_tracker.py --days 7"
echo ""
echo "=============================================="
