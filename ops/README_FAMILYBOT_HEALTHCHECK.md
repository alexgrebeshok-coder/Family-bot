# FamilyBot Healthcheck

Monitors the FamilyBot service and sends alerts to Telegram if issues are detected.

## What It Checks

1. **LaunchAgent Status** - Verifies `com.openclaw.familybot.dialog` is loaded in launchctl
2. **Process Running** - Confirms `bot_dialog.py` process is active
3. **File Freshness** - Checks if `family_state.json` was updated recently (default: 120 min)
4. **Log Errors** - Scans last 200 lines of `~/Library/Logs/familybot_dialog.log` for ERROR/Traceback

## Configuration

### Changing Threshold

Edit `THRESHOLD_MIN` in the healthcheck script:

```bash
nano ~/.openclaw/workspace/ops/familybot_healthcheck.sh
```

Find and modify:
```bash
THRESHOLD_MIN=120  # Change this value (in minutes)
```

After editing, reload the LaunchAgent:
```bash
launchctl unload ~/Library/LaunchAgents/com.openclaw.familybot.healthcheck.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.familybot.healthcheck.plist
```

## Location

- **Script**: `~/.openclaw/workspace/ops/familybot_healthcheck.sh`
- **LaunchAgent**: `~/Library/LaunchAgents/com.openclaw.familybot.healthcheck.plist`
- **Logs**: `~/.openclaw/workspace/logs/familybot_healthcheck.log`

## Disable/Enable

**Disable:**
```bash
launchctl unload ~/Library/LaunchAgents/com.openclaw.familybot.healthcheck.plist
```

**Enable:**
```bash
launchctl load ~/Library/LaunchAgents/com.openclaw.familybot.healthcheck.plist
```

## Schedule

Runs every 3600 seconds (1 hour) automatically via launchd, plus runs immediately when loaded.
