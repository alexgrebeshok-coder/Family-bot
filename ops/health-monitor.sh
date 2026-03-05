#!/bin/bash
# health-monitor.sh - Проверка здоровья OpenClaw системы

LOG_FILE="$HOME/.openclaw/logs/health-monitor.log"
STATE_FILE="$HOME/.openclaw/workspace/memory/heartbeat-state.json"
ALERT_THRESHOLD_CONTEXT=75
ALERT_THRESHOLD_ABORTED=5

log() {
    echo "[$(date -Iseconds)] $1" | tee -a "$LOG_FILE"
}

# 1. Gateway status
check_gateway() {
    if openclaw status &>/dev/null; then
        echo '{"gateway": "ok"}'
        return 0
    else
        echo '{"gateway": "error"}'
        return 1
    fi
}

# 2. Context usage
check_context() {
    local session_file="$HOME/.openclaw/agents/main/sessions/8b1e6e34-3e33-442b-9c71-93861133aea6.jsonl"
    if [ -f "$session_file" ]; then
        local size=$(wc -c < "$session_file")
        local tokens=$((size / 4))  # Примерная оценка
        local percent=$((tokens * 100 / 200000))
        echo "{\"contextPercent\": $percent, \"tokens\": $tokens}"
        
        if [ $percent -gt $ALERT_THRESHOLD_CONTEXT ]; then
            return 1
        fi
    fi
    return 0
}

# 3. Rate limits (проверка через тестовый запрос)
check_rate_limits() {
    # Проверяем что ZAI доступен
    if curl -s -o /dev/null -w "%{http_code}" "https://api.z.ai/api/coding/paas/v4" | grep -q "200\|401"; then
        echo '{"zai": "ok"}'
    else
        echo '{"zai": "error"}'
    fi
}

# 4. Aborted sessions
check_aborted() {
    local aborted=$(grep -r "abortedLastRun.*true" "$HOME/.openclaw/agents/"*/sessions/*.jsonl 2>/dev/null | wc -l)
    echo "{\"abortedSessions\": $aborted}"
    
    if [ $aborted -gt $ALERT_THRESHOLD_ABORTED ]; then
        return 1
    fi
    return 0
}

# Main check
main() {
    log "Starting health check..."
    
    local gateway_status=$(check_gateway)
    local context_status=$(check_context)
    local rate_status=$(check_rate_limits)
    local aborted_status=$(check_aborted)
    
    # Combine into state JSON
    cat > "$STATE_FILE" <<EOF
{
    "lastCheck": "$(date -Iseconds)",
    "gateway": $(echo $gateway_status | jq -r '.gateway'),
    "context": $(echo $context_status | jq -c .),
    "rateLimits": $(echo $rate_status | jq -c .),
    "aborted": $(echo $aborted_status | jq -c .)
}
EOF
    
    log "Health check complete. State saved to $STATE_FILE"
    
    # Alert if needed
    local context_percent=$(echo $context_status | jq -r '.contextPercent // 0')
    if [ $context_percent -gt $ALERT_THRESHOLD_CONTEXT ]; then
        log "⚠️ WARNING: Context usage at ${context_percent}%"
    fi
}

main "$@"
