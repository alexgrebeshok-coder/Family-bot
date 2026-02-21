#!/bin/bash
# OpenClaw Model Ping Script
# Run: ./openclaw_model_ping.sh
# Schedule recommendation: Every 4 hours

set -e

LOG_DIR="/Users/aleksandrgrebeshok/.openclaw/workspace/logs"
LOG_FILE="$LOG_DIR/openclaw_model_ping.log"
TELEGRAM_TARGET="1258992460"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Timestamp
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

echo "[$TIMESTAMP] Starting model ping..." >> "$LOG_FILE"

# Test 1: Try local agent ping
PING_SUCCESS=0
PING_DETAILS=""

echo "[$TIMESTAMP] Test 1: Local agent ping..." >> "$LOG_FILE"

if output=$(openclaw agent --message "ping" --local 2>&1); then
    echo "[$TIMESTAMP] Local agent ping succeeded" >> "$LOG_FILE"
    echo "$output" >> "$LOG_FILE"
    PING_SUCCESS=1
    PING_DETAILS="Local agent: OK"
else
    echo "[$TIMESTAMP] Local agent ping failed" >> "$LOG_FILE"
    echo "$output" >> "$LOG_FILE"
fi

# Test 2: Minimal model invocation (if test 1 failed)
if [ $PING_SUCCESS -eq 0 ]; then
    echo "[$TIMESTAMP] Test 2: Minimal model invocation..." >> "$LOG_FILE"

    if output=$(timeout 30 openclaw agent --message "test" 2>&1); then
        echo "[$TIMESTAMP] Minimal invocation succeeded" >> "$LOG_FILE"
        echo "$output" >> "$LOG_FILE"
        PING_SUCCESS=1
        PING_DETAILS="Fallback invocation: OK"
    else
        echo "[$TIMESTAMP] Minimal invocation failed" >> "$LOG_FILE"
        echo "$output" >> "$LOG_FILE"
    fi
fi

# Send alert if all tests failed
if [ $PING_SUCCESS -eq 0 ]; then
    echo "[$TIMESTAMP] ERROR: All model ping tests failed" >> "$LOG_FILE"
    echo "[$TIMESTAMP] Sending alert to Telegram..." >> "$LOG_FILE"
    openclaw message send --channel telegram --target "$TELEGRAM_TARGET" \
        --message "[OpenClaw Model] Ping failed - models not responding. Check logs: $LOG_FILE" || true
    echo "[$TIMESTAMP] Alert sent" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    exit 1
else
    echo "[$TIMESTAMP] Model ping successful: $PING_DETAILS" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    exit 0
fi
