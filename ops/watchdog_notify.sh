#!/bin/bash
# OpenClaw Watchdog Notification Script
# Sends watchdog alerts to Telegram

# Message is passed as first argument
MESSAGE="$1"

# Send message via openclaw
openclaw message send --channel telegram --target 1258992460 --message "$MESSAGE"
