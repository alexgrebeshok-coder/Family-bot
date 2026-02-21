#!/bin/bash

#############################################
# OpenClaw Watchdog - Gateway Monitor
# Keeps OpenClaw Gateway alive with backoff retries
#############################################

# Configuration
WATCHDOG_LOG="/Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_watchdog.log"
LOCKFILE="/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.lock"
MAX_ATTEMPTS=10
BACKOFF_DELAYS=(5 15 30 60)  # backoff sequence in seconds

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

#############################################
# Lockfile handling
#############################################

acquire_lock() {
    if [ -f "${LOCKFILE}" ]; then
        local pid=$(cat "${LOCKFILE}")
        if ps -p "${pid}" > /dev/null 2>&1; then
            log_warn "Watchdog already running with PID ${pid}"
            echo "ERROR: Watchdog already running (PID: ${pid})"
            exit 1
        else
            log_info "Removing stale lockfile (PID ${pid} not running)"
            rm -f "${LOCKFILE}"
        fi
    fi

    echo $$ > "${LOCKFILE}"
    log_info "Acquired lock (PID: $$)"
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

check_gateway_status() {
    # Returns 0 if gateway is running, 1 otherwise
    openclaw gateway status > /dev/null 2>&1
    return $?
}

restart_gateway() {
    log_info "Attempting to restart gateway..."
    openclaw gateway restart >> "${WATCHDOG_LOG}" 2>&1
    local status=$?
    if [ ${status} -eq 0 ]; then
        log_info "Gateway restart command executed successfully"
    else
        log_error "Gateway restart command failed with exit code ${status}"
    fi
    return ${status}
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
    log_info "=========================================="
    log_info "Watchdog started (PID: $$)"
    log_info "=========================================="

    # Acquire lock to prevent multiple instances
    acquire_lock

    # Check gateway status
    log_info "Checking gateway status..."
    if check_gateway_status; then
        log_info "Gateway is running - exiting cleanly"
        exit 0
    fi

    log_warn "Gateway is NOT running - starting recovery process"

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
                log_info "Gateway recovered successfully!"
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
        log_error "Watchdog FAILED after ${MAX_ATTEMPTS} attempts - gateway not recovered"
        log_info "=========================================="
        exit 1
    fi
}

# Run main
main "$@"
