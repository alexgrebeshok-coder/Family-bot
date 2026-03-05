#!/bin/bash

#############################################
# OpenClaw Watchdog - Gateway Monitor
# Keeps OpenClaw Gateway alive with backoff retries
#############################################

# Configuration
WATCHDOG_LOG="/Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_watchdog.log"
LOCKFILE="/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.lock"
HEARTBEAT_FILE="/Users/aleksandrgrebeshok/.openclaw/workspace/ops/watchdog_heartbeat.ts"
STATE_FILE="/Users/aleksandrgrebeshok/.openclaw/workspace/ops/watchdog_state.txt"
GATEWAY_LABEL="ai.openclaw.gateway"
GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
MAX_ATTEMPTS=10
BACKOFF_DELAYS=(5 15 30 60)  # backoff sequence in seconds
WATCHDOG_NOTIFY_CMD="/Users/aleksandrgrebeshok/.openclaw/workspace/ops/watchdog_notify.sh"  # Optional: command to run for notifications
HEALTH_RETRIES=3
HEALTH_RETRY_DELAY=3
RECOVERY_STABILIZE_TIMEOUT=20
RECOVERY_POLL_INTERVAL=2

# Transparency & Quiet Hours Configuration
QUIET_HEARTBEAT_ONLY=true     # Only suppress heartbeat during quiet hours (critical events always sent)
QUIET_START=22                # Quiet hours start (22:00)
QUIET_END=7                   # Quiet hours end (07:00)
HEARTBEAT_HOURS=6             # Send heartbeat every N hours
TIMEZONE="Asia/Yekaterinburg" # Timezone for quiet hours calculation

#############################################
# Logging functions
#############################################

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" >> "${WATCHDOG_LOG}"
}

log_info() {
    log "INFO" "$@"
}

log_warn() {
    log "WARN" "$@"
}

log_error() {
    log "ERROR" "$@"
}

log_debug() {
    log "DEBUG" "$@"
}

ensure_paths() {
    mkdir -p "$(dirname "${WATCHDOG_LOG}")" "$(dirname "${LOCKFILE}")"
    touch "${WATCHDOG_LOG}"
}

#############################################
# Quiet Hours & Heartbeat Functions
#############################################

# Check if current time is within quiet hours
is_quiet_hours() {
    local current_hour=$(TZ="${TIMEZONE}" date +%H)
    local hour_num=${current_hour#0}  # Remove leading zero for arithmetic

    # Handle overnight quiet hours (19:00 - 07:00)
    if [ "${QUIET_START}" -gt "${QUIET_END}" ]; then
        # Quiet period spans midnight (e.g., 19-07)
        if [ ${hour_num} -ge "${QUIET_START}" ] || [ ${hour_num} -lt "${QUIET_END}" ]; then
            return 0  # Yes, in quiet hours
        fi
    else
        # Normal period (e.g., 02-05)
        if [ ${hour_num} -ge "${QUIET_START}" ] && [ ${hour_num} -lt "${QUIET_END}" ]; then
            return 0  # Yes, in quiet hours
        fi
    fi

    return 1  # Not in quiet hours
}

# Check if heartbeat should be sent (not suppressed)
should_send_heartbeat() {
    if [ "${QUIET_HEARTBEAT_ONLY}" = "true" ] && is_quiet_hours; then
        log_debug "Heartbeat suppressed during quiet hours (${QUIET_START}:00-${QUIET_END}:00)"
        return 1
    fi
    return 0
}

# Send heartbeat if needed (every HEARTBEAT_HOURS)
send_heartbeat_if_needed() {
    local now_epoch=$(date +%s)
    local last_sent=0

    # Read last heartbeat time from file if exists
    if [ -f "${HEARTBEAT_FILE}" ]; then
        last_sent=$(cat "${HEARTBEAT_FILE}")
    fi

    local hours_since_last=$(( (now_epoch - last_sent) / 3600 ))

    # Check if it's time to send heartbeat
    if [ ${hours_since_last} -ge "${HEARTBEAT_HOURS}" ]; then
        if should_send_heartbeat; then
            notify "OpenClaw Watchdog heartbeat: gateway alive, monitoring active (last check: $(date '+%Y-%m-%d %H:%M:%S'))"
            # Update heartbeat timestamp
            echo "${now_epoch}" > "${HEARTBEAT_FILE}"
            log_info "Heartbeat sent and timestamp updated"
        else
            log_debug "Heartbeat skipped (quiet hours)"
            # Still update timestamp to avoid piling up heartbeats
            echo "${now_epoch}" > "${HEARTBEAT_FILE}"
        fi
    else
        log_debug "Heartbeat not due (last sent ${hours_since_last}h ago, interval ${HEARTBEAT_HOURS}h)"
    fi
}

#############################################
# Notification function
#############################################

notify() {
    local message="$*"
    local is_heartbeat=false

    # Check if this is a heartbeat message
    if [[ "${message}" == *"heartbeat"* ]]; then
        is_heartbeat=true
    fi

    # Check if this message should be suppressed
    if [ "${is_heartbeat}" = true ] && ! should_send_heartbeat; then
        log_info "NOTIFY (SUPPRESSED): ${message}"
        return 0
    fi

    # Always log notification
    log_info "NOTIFY: ${message}"

    # Execute notification command if configured
    if [ -n "${WATCHDOG_NOTIFY_CMD}" ]; then
        # Dispatch asynchronously: alerts must never block recovery logic.
        (
            "${WATCHDOG_NOTIFY_CMD}" "${message}" > /dev/null 2>&1
        ) &
        log_debug "Notification dispatched asynchronously"
    fi
}

read_state() {
    if [ -f "${STATE_FILE}" ]; then
        cat "${STATE_FILE}"
    else
        echo "unknown"
    fi
}

write_state() {
    local state="$1"
    echo "${state}" > "${STATE_FILE}"
}

notify_on_state_change() {
    local new_state="$1"
    local message="$2"
    local prev_state
    prev_state="$(read_state)"

    if [ "${prev_state}" != "${new_state}" ]; then
        notify "${message}"
        write_state "${new_state}"
        log_info "State changed: ${prev_state} -> ${new_state}"
    else
        log_debug "State unchanged (${new_state}) - notification skipped"
    fi
}

#############################################
# Lockfile handling
#############################################

acquire_lock() {
    if [ -f "${LOCKFILE}" ]; then
        local pid=$(cat "${LOCKFILE}")
        if ps -p "${pid}" > /dev/null 2>&1; then
            log_warn "Watchdog already running with PID ${pid}"
            return 1
        else
            log_info "Removing stale lockfile (PID ${pid} not running)"
            rm -f "${LOCKFILE}"
        fi
    fi

    echo $$ > "${LOCKFILE}"
    log_info "Acquired lock (PID: $$)"
    return 0
}

release_lock() {
    if [ -f "${LOCKFILE}" ]; then
        rm -f "${LOCKFILE}"
        log_info "Released lock"
    fi
}

cleanup() {
    release_lock
}

# Trap signals for cleanup
trap cleanup EXIT INT TERM

#############################################
# OpenClaw Gateway functions
#############################################

check_gateway_status_once() {
    local quiet="${1:-false}"
    local uid
    uid="$(id -u)"

    # launchd can briefly report non-running during restarts; do not fail solely on this signal.
    if ! launchctl print "gui/${uid}/${GATEWAY_LABEL}" 2>/dev/null | grep -q "state = running"; then
        if [ "${quiet}" != "true" ]; then
            log_debug "Gateway launchd state is not 'running' (transient state allowed)"
        fi
    fi

    if ! lsof -nP -iTCP:"${GATEWAY_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
        if [ "${quiet}" != "true" ]; then
            log_warn "Gateway port ${GATEWAY_PORT} is not listening"
        fi
        return 1
    fi

    # Validate endpoint response to avoid false-positive "port open but dead gateway" states.
    if ! curl -fsS --max-time 2 "http://127.0.0.1:${GATEWAY_PORT}/" >/dev/null 2>&1; then
        if [ "${quiet}" != "true" ]; then
            log_warn "Gateway HTTP probe failed on 127.0.0.1:${GATEWAY_PORT}"
        fi
        return 1
    fi

    return 0
}

check_gateway_status() {
    local attempt=1

    while [ ${attempt} -le ${HEALTH_RETRIES} ]; do
        local quiet="false"
        if [ ${attempt} -gt 1 ]; then
            quiet="true"
        fi

        if check_gateway_status_once "${quiet}"; then
            if [ ${attempt} -gt 1 ]; then
                log_info "Gateway became healthy on retry ${attempt}/${HEALTH_RETRIES}"
            fi
            return 0
        fi

        if [ ${attempt} -lt ${HEALTH_RETRIES} ]; then
            log_debug "Gateway health check retry ${attempt}/${HEALTH_RETRIES} in ${HEALTH_RETRY_DELAY}s"
            sleep "${HEALTH_RETRY_DELAY}"
        fi

        attempt=$((attempt + 1))
    done

    log_warn "Gateway status check failed after ${HEALTH_RETRIES} attempts"
    return 1
}

wait_for_gateway_healthy() {
    local timeout="${1:-${RECOVERY_STABILIZE_TIMEOUT}}"
    local elapsed=0

    while [ ${elapsed} -lt ${timeout} ]; do
        if check_gateway_status_once "true"; then
            return 0
        fi
        sleep "${RECOVERY_POLL_INTERVAL}"
        elapsed=$((elapsed + RECOVERY_POLL_INTERVAL))
    done

    return 1
}

is_gateway_service_loaded() {
    local uid
    uid="$(id -u)"
    launchctl print "gui/${uid}/${GATEWAY_LABEL}" >/dev/null 2>&1
}

restart_gateway() {
    log_info "Attempting gateway recovery (restart -> start -> install+start)"

    # Fast-path for the common failure mode in logs: service unit disappeared after stop/crash.
    if ! is_gateway_service_loaded; then
        log_warn "Gateway service is not loaded; skipping restart/start and running install-first recovery"
        openclaw gateway install --force >> "${WATCHDOG_LOG}" 2>&1 || true
        if wait_for_gateway_healthy; then
            log_info "Gateway recovery succeeded via install --force (service was not loaded)"
            return 0
        fi

        log_warn "Install --force did not recover gateway, trying explicit start..."
        openclaw gateway start >> "${WATCHDOG_LOG}" 2>&1 || true
        if wait_for_gateway_healthy; then
            log_info "Gateway recovery succeeded via install + start (service was not loaded)"
            return 0
        fi

        log_error "Install/start path failed while service was not loaded"
        return 1
    fi

    openclaw gateway restart >> "${WATCHDOG_LOG}" 2>&1 || true
    if wait_for_gateway_healthy; then
        log_info "Gateway recovery succeeded via restart"
        return 0
    fi

    log_warn "Restart did not recover gateway, trying start..."
    openclaw gateway start >> "${WATCHDOG_LOG}" 2>&1 || true
    if wait_for_gateway_healthy; then
        log_info "Gateway recovery succeeded via start"
        return 0
    fi

    log_warn "Start did not recover gateway, trying install + start..."
    openclaw gateway install --force >> "${WATCHDOG_LOG}" 2>&1 || true
    if wait_for_gateway_healthy; then
        log_info "Gateway recovery succeeded via install --force"
        return 0
    fi

    log_warn "Install --force did not recover gateway, trying explicit start..."
    openclaw gateway start >> "${WATCHDOG_LOG}" 2>&1 || true
    if wait_for_gateway_healthy; then
        log_info "Gateway recovery succeeded via install + start"
        return 0
    fi

    log_error "All gateway recovery commands failed"
    return 1
}

wait_and_check() {
    local delay=$1
    log_info "Waiting ${delay}s before recheck..."
    sleep "${delay}"
    check_gateway_status
}

#############################################
# Main watchdog logic
#############################################

main() {
    ensure_paths

    log_info "=========================================="
    log_info "Watchdog started (PID: $$)"
    log_info "=========================================="

    # Acquire lock to prevent multiple instances
    if ! acquire_lock; then
        log_info "Another watchdog instance is active, skipping this interval"
        exit 0
    fi

    # Check gateway status
    log_info "Checking gateway status..."
    if check_gateway_status; then
        log_info "Gateway is running - exiting cleanly"
        write_state "up"
        # Send heartbeat if due
        send_heartbeat_if_needed
        exit 0
    fi

    # Notify: gateway down detected
    log_warn "Gateway is NOT running - starting recovery process"
    notify_on_state_change "down" "OpenClaw Watchdog: gateway DOWN detected, starting recovery..."

    # Recovery loop with backoff
    local attempt=0
    local backoff_index=0
    local success=false

    while [ ${attempt} -lt ${MAX_ATTEMPTS} ] && [ "${success}" = false ]; do
        attempt=$((attempt + 1))
        local delay=${BACKOFF_DELAYS[$((backoff_index % ${#BACKOFF_DELAYS[@]}))]}

        log_info "Recovery attempt ${attempt}/${MAX_ATTEMPTS} (backoff: ${delay}s)"

        # Try to restart gateway
        if restart_gateway; then
            # Wait and recheck
            if wait_and_check "${delay}"; then
                # Notify: restart successful
                log_info "Gateway recovered successfully!"
                notify_on_state_change "up" "OpenClaw Watchdog: gateway recovered after ${attempt} attempt(s)"
                success=true
            else
                log_warn "Gateway still not running after restart"
            fi
        else
            log_warn "Failed to execute restart command"
        fi

        # Increment backoff for next attempt
        backoff_index=$((backoff_index + 1))

        # If not successful and more attempts remain, wait before next attempt
        if [ "${success}" = false ] && [ ${attempt} -lt ${MAX_ATTEMPTS} ]; then
            local next_delay=${BACKOFF_DELAYS[$((backoff_index % ${#BACKOFF_DELAYS[@]}))]}
            log_info "Waiting ${next_delay}s before next attempt..."
            sleep "${next_delay}"
        fi
    done

    # Final status
    log_info "=========================================="
    if [ "${success}" = true ]; then
        log_info "Watchdog completed successfully - gateway is running"
        log_info "=========================================="
        exit 0
    else
        # Notify: fatal after N attempts
        log_error "Watchdog FAILED after ${MAX_ATTEMPTS} attempts - gateway not recovered"
        notify "OpenClaw Watchdog: FATAL - failed to recover gateway after ${MAX_ATTEMPTS} attempts"
        log_info "=========================================="
        exit 1
    fi
}

# Run main
main "$@"
