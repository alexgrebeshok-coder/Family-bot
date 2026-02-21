#!/bin/bash
# OpenClaw Security Audit Script
# Run: ./openclaw_security_audit.sh
# Schedule recommendation: Daily at 02:00 AM

set -e

LOG_DIR="/Users/aleksandrgrebeshok/.openclaw/workspace/logs"
LOG_FILE="$LOG_DIR/openclaw_security_audit.log"
TELEGRAM_TARGET="1258992460"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Timestamp
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

echo "[$TIMESTAMP] Starting security audit..." >> "$LOG_FILE"

# Run security audit
if openclaw security audit --json >> "$LOG_FILE" 2>&1; then
    AUDIT_EXIT_CODE=0
else
    AUDIT_EXIT_CODE=$?
    echo "[$TIMESTAMP] ERROR: Security audit command failed with exit code $AUDIT_EXIT_CODE" >> "$LOG_FILE"
fi

# Check for issues in the output
ISSUES_FOUND=0
ISSUE_SUMMARY=""

if [ $AUDIT_EXIT_CODE -ne 0 ]; then
    ISSUES_FOUND=1
    ISSUE_SUMMARY="Audit command failed (exit code: $AUDIT_EXIT_CODE)"
fi

# Look for WARNING or FAIL in the log
if grep -iE "(WARNING|FAIL|ERROR)" "$LOG_FILE" | tail -20 > /tmp/audit_issues.txt; then
    ISSUES_COUNT=$(wc -l < /tmp/audit_issues.txt)
    if [ $ISSUES_COUNT -gt 0 ]; then
        ISSUES_FOUND=1
        ISSUE_SUMMARY="Found $ISSUES_COUNT issue(s) in security audit"
        echo "[$TIMESTAMP] Issues detected: $ISSUES_COUNT" >> "$LOG_FILE"
        cat /tmp/audit_issues.txt >> "$LOG_FILE"
    fi
fi

# Send alert if issues found
if [ $ISSUES_FOUND -eq 1 ]; then
    echo "[$TIMESTAMP] Sending alert to Telegram..." >> "$LOG_FILE"
    openclaw message send --channel telegram --target "$TELEGRAM_TARGET" \
        --message "[OpenClaw Security] $ISSUE_SUMMARY. Check logs: $LOG_FILE" || true
    echo "[$TIMESTAMP] Alert sent" >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] Security audit passed - no issues found" >> "$LOG_FILE"
fi

echo "[$TIMESTAMP] Security audit completed" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

exit 0
