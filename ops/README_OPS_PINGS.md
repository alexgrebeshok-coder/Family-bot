# OpenClaw OPS Scripts - Security Audit & Model Ping

## Overview

Two automated monitoring scripts for OpenClaw operations:

1. **openclaw_security_audit.sh** - Runs security audit and alerts on issues
2. **openclaw_model_ping.sh** - Tests model availability and alerts on failures

## Location

- Scripts: `/Users/aleksandrgrebeshok/.openclaw/workspace/ops/`
- Logs: `/Users/aleksandrgrebeshok/.openclaw/workspace/logs/`

## Scripts

### 1. openclaw_security_audit.sh

**Purpose:** Runs OpenClaw security audit and sends Telegram alerts if WARNING or FAIL issues are detected.

**Usage:**
```bash
./openclaw_security_audit.sh
```

**What it does:**
- Runs `openclaw security audit --json`
- Logs output to `logs/openclaw_security_audit.log`
- Detects WARNING/FAIL/ERROR in output
- Sends Telegram alert if issues found
- Logs all activity with timestamps

**Schedule recommendation:** Daily at 02:00 AM

---

### 2. openclaw_model_ping.sh

**Purpose:** Tests model availability (ZAI → fallback) and alerts if models are not responding.

**Usage:**
```bash
./openclaw_model_ping.sh
```

**What it does:**
- Test 1: Local agent ping with `--local` flag
- Test 2: Minimal agent invocation (fallback if test 1 fails)
- Logs results to `logs/openclaw_model_ping.log`
- Sends Telegram alert if all tests fail
- Exits with code 1 on failure, 0 on success

**Schedule recommendation:** Every 4 hours

## Setting Up Schedules

### Option A: Using cron

Edit crontab:
```bash
crontab -e
```

Add entries:
```cron
# Security audit - daily at 02:00 AM
0 2 * * * /Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_security_audit.sh

# Model ping - every 4 hours
0 */4 * * * /Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_model_ping.sh
```

### Option B: Using launchd (macOS)

Create `~/Library/LaunchAgents/com.openclaw.security-audit.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.security-audit</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_security_audit.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/aleksandrgrebeshok/.openclaw/workspace/logs/security-audit.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/aleksandrgrebeshok/.openclaw/workspace/logs/security-audit.stderr.log</string>
</dict>
</plist>
```

Create `~/Library/LaunchAgents/com.openclaw.model-ping.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.model-ping</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_model_ping.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>0</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StartInterval</key>
    <integer>14400</integer>
    <key>StandardOutPath</key>
    <string>/Users/aleksandrgrebeshok/.openclaw/workspace/logs/model-ping.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/aleksandrgrebeshok/.openclaw/workspace/logs/model-ping.stderr.log</string>
</dict>
</plist>
```

Load the agents:
```bash
launchctl load ~/Library/LaunchAgents/com.openclaw.security-audit.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.model-ping.plist
```

Unloading:
```bash
launchctl unload ~/Library/LaunchAgents/com.openclaw.security-audit.plist
launchctl unload ~/Library/LaunchAgents/com.openclaw.model-ping.plist
```

## Telegram Alerts

Both scripts send alerts to Telegram channel ID: `1258992460`

Alert format:
- Security: `[OpenClaw Security] ...`
- Model: `[OpenClaw Model] ...`

## Log Files

- `logs/openclaw_security_audit.log` - Security audit results
- `logs/openclaw_model_ping.log` - Model ping results

Logs include timestamps and are appended (not overwritten).

## Manual Testing

Test scripts manually before enabling schedules:
```bash
# Test security audit
cd /Users/aleksandrgrebeshok/.openclaw/workspace/ops
./openclaw_security_audit.sh

# Test model ping
./openclaw_model_ping.sh

# Check logs
tail -f /Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_security_audit.log
tail -f /Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_model_ping.log
```

## Troubleshooting

**No alerts sent?**
- Check `openclaw message send` is working
- Verify Telegram target ID is correct
- Check script exit codes and logs

**Scripts failing to run?**
- Ensure scripts are executable: `chmod +x *.sh`
- Check file paths are correct
- Verify `openclaw` CLI is in PATH

**Logs not created?**
- Ensure logs directory exists
- Check write permissions
- Verify script is running

## Notes

- Scripts use `set -e` for error handling
- Scripts create log directory if missing
- Alerts only sent on issues, not on success
- No test messages sent during setup
