#!/bin/bash
# audio-briefing.sh — Утренняя аудиосводка
# Запуск: ./briefing.sh [output.mp3]

set -e

# Активируем venv семейного бота
VENV="/Users/aleksandrgrebeshok/.openclaw/workspace/Проекты/Семейный Бот/.venv"
if [ -d "$VENV" ]; then
    source "$VENV/bin/activate"
fi

OUTPUT="${1:-/tmp/morning_briefing.aiff}"
MP3_OUTPUT="${OUTPUT%.aiff}.mp3"

echo "🎙️ Генерирую утреннюю сводку..."

# 1. Получаем погоду
echo "🌤️ Погода..."
WEATHER=$(curl -s "https://api.open-meteo.com/v1/forecast?latitude=61.25&longitude=73.43&current=temperature_2m,weather_code" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); t=d['current']['temperature_2m']; print(f'Температура в Сургуте: {t} градусов')")

# 2. Получаем новости (фильтруем негатив)
echo "📰 Новости..."
NEWS=$(curl -s "https://siapress.ru/rss" | \
  python3 -c "
import sys, feedparser, re
feed = feedparser.parse(sys.stdin.read())
negative = ['убий', 'смерть', 'погиб', 'краж', 'мошенн', 'скандал', 'уголов', 'суд ', 'арест']
items = []
for e in feed.entries[:5]:
    t = e.get('title', '')
    if not any(n in t.lower() for n in negative):
        items.append(t)
print('. '.join(items[:3]))
")

# 3. Reddit Digest (топ посты)
echo "📱 Reddit..."
REDDIT=$(/Users/aleksandrgrebeshok/.openclaw/skills/reddit-digest/reddit-digest.sh 2>/dev/null | head -20)

# 4. Дата и праздник
echo "📅 Дата..."
DATE=$(date +"%d %B, %A" | sed 's/Monday/понедельник/;s/Tuesday/вторник/;s/Wednesday/среда/;s/Thursday/четверг/;s/Friday/пятница/;s/Saturday/суббота/;s/Sunday/воскресенье/')

# 5. Собираем текст
TEXT="Доброе утро! Сегодня $DATE. $WEATHER. В новостях: $NEWS. Хорошего дня!"

# 6. Текстовый дайджест для Telegram (расширенный)
DIGEST_TEXT="☀️ *Утренний дайджест* — $DATE

🌤️ *Погода:*
$WEATHER

📰 *Новости:*
$NEWS

📱 *Reddit:*
\`\`\`
$REDDIT
\`\`\`

Хорошего дня! 🎉"

echo "📝 Текст сводки:"
echo "$TEXT"
echo ""

# 5. Генерируем аудио (macOS say)
echo "🔊 Генерирую аудио..."
say -v Milena -o "$OUTPUT" "$TEXT"

# 6. Конвертируем в MP3 если есть ffmpeg
if command -v ffmpeg &> /dev/null; then
    ffmpeg -y -i "$OUTPUT" -codec:a libmp3lame -qscale:a 2 "$MP3_OUTPUT" 2>/dev/null
    echo "✅ Готово: $MP3_OUTPUT"
    echo "📊 Размер: $(du -h "$MP3_OUTPUT" | cut -f1)"
else
    echo "✅ Готово: $OUTPUT (AIFF)"
    echo "💡 Установи ffmpeg для конвертации в MP3"
fi

# Выводим путь для использования
echo ""
echo "📁 Путь к файлу: ${MP3_OUTPUT:-$OUTPUT}"

# 7. Отправляем текстовый дайджест в Telegram (если есть TELEGRAM_TOKEN)
if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    echo "📤 Отправляю в Telegram..."
    curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="$DIGEST_TEXT" \
        -d parse_mode="Markdown" \
        > /dev/null
    echo "✅ Отправлено"
fi
