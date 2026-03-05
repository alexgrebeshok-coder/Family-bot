#!/bin/bash
# FamilyBot Healthcheck Script
# Runs hourly via LaunchAgent, sends alerts to Telegram if issues detected

set -euo pipefail

# Configuration
THRESHOLD_MIN=120
LOG_DIR="/Users/aleksandrgrebeshok/.openclaw/workspace/logs"
HEALTHCHECK_LOG="$LOG_DIR/familybot_healthcheck.log"
BOT_LOG="/tmp/family_bot.log"
FAMILY_STATE_PATH="/Users/aleksandrgrebeshok/.openclaw/workspace/Проекты/Семейный Бот/data/family_state.json"
TELEGRAM_TARGET="1258992460"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Timestamp for logs
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Function to log to healthcheck log
log() {
    echo "[$TIMESTAMP] $1" >> "$HEALTHCHECK_LOG"
}

# Function to send Telegram alert
send_alert() {
    local message="[FamilyBot] $1"
    log "ALERT: $message"
    /opt/homebrew/bin/openclaw message send --channel telegram --target "$TELEGRAM_TARGET" --message "$message" 2>/dev/null || log "Failed to send Telegram alert"
}

# Initialize issue counter
ISSUES=0
ISSUE_MESSAGES=()

# Check 1: launchctl list for com.familybot.dialog (updated name)
log "Checking launchctl status for com.familybot.dialog..."
LAUNCHCTL_CHECK=$(launchctl list 2>/dev/null | grep "com.familybot.dialog" || echo "")
if [ -z "$LAUNCHCTL_CHECK" ]; then
    ISSUES=$((ISSUES + 1))
    ISSUE_MESSAGES+=("LaunchAgent com.familybot.dialog not found in launchctl list")
    log "ERROR: LaunchAgent not found"
else
    log "OK: LaunchAgent is loaded ($LAUNCHCTL_CHECK)"
fi

# Check 2: bot_dialog.py process exists
log "Checking for bot_dialog.py process..."
if ! pgrep -f "bot_dialog.py" > /dev/null; then
    ISSUES=$((ISSUES + 1))
    ISSUE_MESSAGES+=("Process bot_dialog.py not running")
    log "ERROR: bot_dialog.py process not found"
else
    log "OK: bot_dialog.py process running"
fi

# Check 3: family_state.json file age
log "Checking family_state.json age..."
if [ ! -f "$FAMILY_STATE_PATH" ]; then
    ISSUES=$((ISSUES + 1))
    ISSUE_MESSAGES+=("family_state.json not found at $FAMILY_STATE_PATH")
    log "ERROR: family_state.json file not found"
else
    FILE_MTIME=$(stat -f %m "$FAMILY_STATE_PATH" 2>/dev/null || stat -c %Y "$FAMILY_STATE_PATH" 2>/dev/null)
    CURRENT_TIME=$(date +%s)
    FILE_AGE_MIN=$(( (CURRENT_TIME - FILE_MTIME) / 60 ))
    
    if [ $FILE_AGE_MIN -gt $THRESHOLD_MIN ]; then
        ISSUES=$((ISSUES + 1))
        ISSUE_MESSAGES+=("family_state.json not updated for ${FILE_AGE_MIN} minutes (threshold: ${THRESHOLD_MIN} min)")
        log "ERROR: family_state.json is stale (${FILE_AGE_MIN} min old)"
    else
        log "OK: family_state.json updated ${FILE_AGE_MIN} minutes ago"
    fi
fi

# Check 4: Errors in bot log
log "Checking for errors in bot log..."
if [ -f "$BOT_LOG" ]; then
    ERROR_COUNT=$(tail -n 200 "$BOT_LOG" | grep -cE "(ERROR|Traceback)" 2>/dev/null || echo "0")
    ERROR_COUNT=$(echo "$ERROR_COUNT" | tr -d '[:space:]')
    if [ "$ERROR_COUNT" -gt 0 ] 2>/dev/null; then
        ISSUES=$((ISSUES + 1))
        ERROR_PREVIEW=$(tail -n 200 "$BOT_LOG" | grep -E "(ERROR|Traceback)" | tail -n 3 | head -c 200)
        ISSUE_MESSAGES+=("Found ${ERROR_COUNT} ERROR/Traceback in log (last: ${ERROR_PREVIEW})")
        log "ERROR: Found $ERROR_COUNT errors in log"
    else
        log "OK: No errors in last 200 lines"
    fi
else
    log "WARNING: Bot log file not found at $BOT_LOG"
fi

# Send alert if any issues detected
if [ $ISSUES -gt 0 ]; then
    ALERT_MESSAGE="Healthcheck failed: $ISSUES issue(s) detected. "
    for msg in "${ISSUE_MESSAGES[@]}"; do
        ALERT_MESSAGE+="$msg | "
    done
    send_alert "$ALERT_MESSAGE"
    log "Healthcheck completed with $ISSUES issue(s)"
else
    log "Healthcheck completed: All checks passed"
fi

exit 0
