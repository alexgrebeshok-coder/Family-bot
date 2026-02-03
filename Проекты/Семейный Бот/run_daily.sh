#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/Users/aleksandrgrebeshok/.openclaw/workspace/Проекты/Семейный Бот"
LOG_FILE="/tmp/family_bot.log"

cd "$PROJECT_DIR"
source .venv/bin/activate

attempt=1
max_attempts=3
while true; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] attempt $attempt" >> "$LOG_FILE"
  if python main.py >> "$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] success" >> "$LOG_FILE"
    exit 0
  fi
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] failure" >> "$LOG_FILE"
  if [ $attempt -ge $max_attempts ]; then
    # notify via OpenClaw wake so you see it immediately
    openclaw gateway wake --text "Family bot failed after $max_attempts attempts. Check /tmp/family_bot.log" --mode now || true
    exit 1
  fi
  attempt=$((attempt+1))
  sleep 30

done
