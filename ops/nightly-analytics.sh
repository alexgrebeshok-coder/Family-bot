#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/tmp/openclaw-analytics"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/nightly-$(date +%Y-%m-%d).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "========================================="
echo "Nightly Analytics - $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
echo ""

# 1. OpenClaw Status
echo "📊 OpenClaw Status:"
echo "---"
openclaw status | head -30
echo ""

# 2. Gateway Health
echo "🔗 Gateway Status:"
echo "---"
if openclaw gateway status 2>/dev/null | grep -q "running"; then
    echo "✅ Gateway running"
else
    echo "❌ Gateway NOT running"
fi
echo ""

# 3. Active Sessions
echo "🤖 Active Sessions:"
echo "---"
openclaw status | grep -A 20 "Sessions:" | head -15
echo ""

# 4. Aborted Sessions Check
echo "⚠️ Aborted Sessions:"
echo "---"
ABORTED=$(openclaw status | grep -c "aborted" || echo "0")
echo "Count: $ABORTED"
if [ "$ABORTED" -gt 5 ]; then
    echo "⚠️ WARNING: High number of aborted sessions"
fi
echo ""

# 5. Memory Usage
echo "💾 Memory Usage:"
echo "---"
vm_stat | head -5
echo ""
top -l 1 -s 0 | grep PhysMem
echo ""

# 6. Family Bot Status
echo "🤖 Family Bot:"
echo "---"
if [ -f /tmp/familybot_daily.log ]; then
    LAST_POST=$(tail -20 /tmp/familybot_daily.log | grep -i "отправлено\|sent\|posted" | tail -1 || echo "No posts found")
    echo "Last post: $LAST_POST"
else
    echo "⚠️ Log file not found: /tmp/familybot_daily.log"
fi
echo ""

# 7. Projects List
echo "📁 Projects:"
echo "---"
find ~/.openclaw/workspace/Проекты -maxdepth 2 -type f -name "*.py" 2>/dev/null | head -10
echo ""

# 8. Rate Limits (via session status)
echo "🚦 Rate Limits:"
echo "---"
session_status 2>/dev/null | grep -i "usage\|tokens" | head -10 || echo "No rate limit data"
echo ""

# 9. Recent Errors
echo "❌ Recent Errors (gateway logs):"
echo "---"
openclaw logs --limit 50 2>/dev/null | grep -i "error\|failed\|aborted" | tail -10 || echo "No errors found"
echo ""

echo "========================================="
echo "End of Analytics - $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
