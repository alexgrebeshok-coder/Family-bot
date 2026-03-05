#!/bin/bash

# ============================================
# Тестовый скрипт для сравнения Gemini моделей
# ============================================
# Сравнивает:
# - openrouter/google/gemini-2.5-flash-lite
# - openrouter/google/gemini-3.1-flash-lite-preview
#
# Проверяет:
# - Скорость ответа (3 теста разной сложности)
# - Наличие ошибок/timeout
# - Выводит сравнительную таблицу
# ============================================

# Настройки
API_URL="https://openrouter.ai/api/v1/chat/completions"
TIMEOUT=30  # секунд на запрос
MODEL_1="google/gemini-2.5-flash-lite"
MODEL_2="google/gemini-3.1-flash-lite-preview"

# Проверка API ключа
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "❌ Ошибка: OPENROUTER_API_KEY не установлен"
    echo "Установите: export OPENROUTER_API_KEY='your-key'"
    exit 1
fi

# Тестовые запросы (от простого к сложному)
declare -a TESTS=(
    "What is 2+2?"
    "List 5 programming languages"
    "Explain recursion in 2 sentences"
)

# Функция для тестирования модели
test_model() {
    local model=$1
    local model_name=$2
    local -a results=()
    local total_time=0
    local errors=0
    
    echo "Тестируем $model_name..." >&2
    
    for i in "${!TESTS[@]}"; do
        local prompt="${TESTS[$i]}"
        local test_num=$((i + 1))
        
        # Замеряем время
        local start=$(date +%s.%N 2>/dev/null || gdate +%s.%N 2>/dev/null)
        
        # Делаем запрос
        local response=$(curl -s -w "\n%{http_code}" --max-time $TIMEOUT \
            -X POST "$API_URL" \
            -H "Authorization: Bearer $OPENROUTER_API_KEY" \
            -H "Content-Type: application/json" \
            -d "{
                \"model\": \"$model\",
                \"messages\": [{\"role\": \"user\", \"content\": \"$prompt\"}],
                \"max_tokens\": 100
            }" 2>&1)
        
        local exit_code=$?
        local end=$(date +%s.%N 2>/dev/null || gdate +%s.%N 2>/dev/null)
        local duration=$(echo "$end - $start" | bc 2>/dev/null || echo "0")
        local duration_rounded=$(printf "%.2f" "$duration" 2>/dev/null || echo "0")
        
        # Проверяем результат
        if [ $exit_code -eq 0 ]; then
            local http_code=$(echo "$response" | tail -n1)
            local body=$(echo "$response" | sed '$d')
            
            # Проверяем на ошибки в ответе
            if [ "$http_code" = "200" ] && ! echo "$body" | grep -q "error"; then
                results+=("OK ${duration_rounded}s")
                total_time=$(echo "$total_time + $duration" | bc 2>/dev/null || echo "$total_time")
            else
                results+=("ERROR")
                ((errors++))
            fi
        else
            results+=("TIMEOUT")
            ((errors++))
        fi
    done
    
    # Вычисляем среднее время (только для успешных)
    local avg_time="0"
    local success_count=$((3 - errors))
    if [ $success_count -gt 0 ]; then
        avg_time=$(echo "scale=2; $total_time / $success_count" | bc 2>/dev/null || echo "0")
    fi
    
    # Выводим результат
    printf "%-6s | %-8s | %-8s | %-8s | %-8s | %d\n" \
        "$model_name" "${results[0]}" "${results[1]}" "${results[2]}" "${avg_time}s" "$errors"
}

# ============================================
# Главная часть
# ============================================

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Сравнение Gemini моделей"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "Модели:"
echo "  2.5 = gemini-2.5-flash-lite"
echo "  3.1 = gemini-3.1-flash-lite-preview"
echo ""
echo "Тесты:"
echo "  1. What is 2+2? (простой)"
echo "  2. List 5 programming languages (средний)"
echo "  3. Explain recursion in 2 sentences (сложнее)"
echo ""
echo "────────────────────────────────────────────────────────────────"
printf "%-6s | %-8s | %-8s | %-8s | %-8s | %s\n" \
    "Model" "Test 1" "Test 2" "Test 3" "Avg Time" "Errors"
echo "────────────────────────────────────────────────────────────────"

# Тестируем обе модели
test_model "$MODEL_1" "2.5"
test_model "$MODEL_2" "3.1"

echo "────────────────────────────────────────────────────────────────"
echo ""
echo "✅ Тест завершен"
echo ""
