# MEMORY.md

## Ключевое (кратко)
- Проект: семейный Telegram‑бот (Python) в /Users/aleksandrgrebeshok/.openclaw/workspace/Проекты/Семейный Бот/.
- LLM: OpenRouter (z-ai/glm-4.5-air:free). Погода: Open‑Meteo (Сургут/Тюмень/Москва). Новости: RSS (siapress.ru, interfax.ru). Постинг в Telegram.
- Расписание: ежедневный автозапуск в 07:30 Asia/Yekaterinburg через local cron + run_daily.sh (ретраи, лог /tmp/family_bot.log, wake при сбое).
- Чат для постинга: супергруппа «Семья», chat_id = -1003880864767.
- Правило: входящие аудио/voice по умолчанию расшифровывать через whisper‑cpp (whisper‑cli).
