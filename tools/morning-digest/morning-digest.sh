#!/bin/bash
# morning-digest.sh — Полный утренний дайджест
# Запускается в 07:30 через cron

set -e

REDDIT_SCRIPT="/Users/aleksandrgrebeshok/.openclaw/skills/reddit-digest/reddit-digest.sh"
YOUTUBE_SCRIPT="/Users/aleksandrgrebeshok/.openclaw/skills/youtube-digest/youtube-digest.sh"
BRIEFING_SCRIPT="/Users/aleksandrgrebeshok/.openclaw/workspace/tools/audio-briefing/briefing.sh"

# Telegram credentials (из env или семейного бота)
TELEGRAM_TOKEN="${TELEGRAM_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

DATE=$(date +"%d %B" | sed 's/January/января/;s/February/февраля/;s/March/марта/;s/April/апреля/;s/May/мая/;s/June/июня/;s/July/июля/;s/August/августа/;s/September/сентября/;s/October/октября/;s/November/ноября/;s/December/декабря/')
WEEKDAY=$(date +"%A" | sed 's/Monday/понедельник/;s/Tuesday/вторник/;s/Wednesday/среда/;s/Thursday/четверг/;s/Friday/пятница/;s/Saturday/суббота/;s/Sunday/воскресенье/')

echo "☀️ Утренний дайджест — $DATE, $WEEKDAY"
echo "========================================"

# 1. Погода (Сургут)
echo "🌤️ Погода..."
WEATHER=$(curl -s "https://api.open-meteo.com/v1/forecast?latitude=61.25&longitude=73.43&current=temperature_2m,weather_code,wind_speed_10m" | \
  python3 -c "
import sys, json
d = json.load(sys.stdin)
t = d['current']['temperature_2m']
w = d['current'].get('wind_speed_10m', 0)
code = d['current'].get('weather_code', 0)

# Коды погоды
weather_codes = {
    0: 'ясно', 1: 'малооблачно', 2: 'переменная облачность', 3: 'облачно',
    45: 'туман', 48: 'изморозь', 51: 'морось', 61: 'дождь', 71: 'снег', 95: 'гроза'
}
desc = weather_codes.get(code, '')
print(f'Сургут: {t}°C, {desc}, ветер {w:.0f} км/ч')
" 2>/dev/null || echo "Погода недоступна")

# 2. Новости (простой парсинг RSS без feedparser)
echo "📰 Новости..."
NEWS=$(curl -s "https://siapress.ru/rss" | \
  grep -o '<title>[^<]*</title>' | \
  sed 's/<title>//;s/<\/title>//' | \
  grep -v "СИА-ПРЕСС" | \
  head -3 | \
  awk '{print "• " $0}' 2>/dev/null || echo "• Новости недоступны")

# 3. Reddit Digest
echo "📱 Reddit..."
REDDIT=$($REDDIT_SCRIPT 2>/dev/null | head -15 || echo "Reddit недоступен")

# 4. YouTube Digest (если настроен)
echo "📺 YouTube..."
if [ -s "$(dirname "$YOUTUBE_SCRIPT")/channels.txt" ] && grep -qv '^#' "$(dirname "$YOUTUBE_SCRIPT")/channels.txt" 2>/dev/null; then
    YOUTUBE=$($YOUTUBE_SCRIPT 2>/dev/null | head -10 || echo "")
else
    YOUTUBE="_Настройте channels.txt_"
fi

# 5. Собираем полный дайджест
DIGEST="☀️ *Утренний дайджест*
📅 $DATE, $WEEKDAY

🌤️ *Погода:*
$WEATHER

📰 *Новости Сургута:*
$NEWS

📱 *Reddit Digest:*
\`\`\`
$REDDIT
\`\`\`

📺 *YouTube:*
$YOUTUBE

---
_Автоматический дайджест от OpenClaw_"

# 6. Выводим
echo ""
echo "$DIGEST"
echo ""

# 7. Отправляем в Telegram (если есть токен)
if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    echo "📤 Отправляю в Telegram..."
    curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="$DIGEST" \
        -d parse_mode="Markdown" \
        > /dev/null && echo "✅ Отправлено"
fi

# 8. Генерируем аудио (если есть время)
if [ -x "$BRIEFING_SCRIPT" ]; then
    echo "🔊 Генерирую аудио..."
    "$BRIEFING_SCRIPT" /tmp/morning_briefing.aiff 2>/dev/null || true
fi

echo ""
echo "✅ Дайджест готов!"
