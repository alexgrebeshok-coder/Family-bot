# MEMORY.md

## Ключевое (кратко)
- Проект: семейный Telegram‑бот (Python) в /Users/aleksandrgrebeshok/.openclaw/workspace/Проекты/Семейный Бот/.
- LLM: OpenRouter (z-ai/glm-4.5-air:free). Погода: Open‑Meteo (Сургут/Тюмень/Москва). Новости: RSS (siapress.ru, interfax.ru). Постинг в Telegram.
- Расписание: ежедневный автозапуск в 07:30 Asia/Yekaterinburg через local cron + run_daily.sh (ретраи, лог /tmp/family_bot.log, wake при сбое).
- Чат для постинга: супергруппа «Семья», chat_id = -1003880864767.
- Правило: входящие аудио/voice по умолчанию расшифровывать через whisper‑cpp (whisper‑cli).

# MEMORY.md

## Ключевое (кратко)
- Проект: семейный Telegram‑бот (Python) в /Users/aleksandrgrebeshok/.openclaw/workspace/Проекты/Семейный Бот/.
- LLM: OpenRouter (z-ai/glm-4.5-air:free). Погода: Open‑Meteo (Сургут/Тюмень/Москва). Новости: RSS (siapress.ru, interfax.ru). Постинг в Telegram.
- Расписание: ежедневный автозапуск в 07:30 Asia/Yekaterinburg через local cron + run_daily.sh (ретраи, лог /tmp/family_bot.log, wake при сбое).
- Чат для постинга: супергруппа «Семья», chat_id = -1003880864767.
- Правило: входящие аудио/voice по умолчанию расшифровывать через whisper‑cpp (whisper‑cli).

## Архитектура агентов (обновлено 24.02.2026)

### Команда (7 агентов):

| Агент | Модель | Провайдер | Роль |
|-------|--------|-----------|------|
| **main** | glm-5 | ZAI Pro ($15) | Оркестратор, общение с пользователем |
| **main-worker** | glm-4.7 | ZAI | Исполнитель (exec, write, edit) |
| **quick-research** | gemini-2.5-flash-lite | OpenRouter ($0) | Research, web поиск |
| **quick-coder** | gemini-2.5-flash-lite | OpenRouter ($0) | Генерация кода |
| **quick-writer** | gemini-2.5-flash-lite | OpenRouter ($0) | Тексты, документация |
| **planner** | gemini-2.5-flash-lite | OpenRouter ($0) | Планирование задач |
| **main-reviewer** | glm-4.7-flash | ZAI | Критика, проверка качества |

### Результаты тестов параллельных агентов (24.02.2026):

| Провайдер | Модель | 1 агент | 2 параллельно | Скорость |
|-----------|--------|---------|---------------|----------|
| **ZAI Pro** | glm-4.7-flash | ✅ | ✅ 1/2 | 42с |
| **OpenRouter** | gemini-2.5-flash-lite | ✅ | ✅ 2/2 | 21с (в 2x быстрее) |
| **OpenRouter free** | qwen3, deepseek | ❌ timeout | ❌ | — |

### Pipeline архитектура (3-stage):

```
Stage 1: Research (2 параллельно, Gemini, ~30с)
    ↓
Stage 2: Execution (1-2 последовательно, ZAI, ~2мин)
    ↓
Stage 3: Review (2 параллельно, Gemini, ~15с)
```

**Выгода:** ~3 минуты вместо 10+ минут последовательно (3x быстрее)

### Ограничения:
- **MacBook Pro M1 32GB** — до 16 параллельных агентов ✅
- Gemini Lite: 2 стабильных параллельно
- ZAI Pro: 1-2 стабильных параллельно
- OpenRouter free: rate-limited, не использовать

### Бюджет: ~$15/мес (ZAI Pro) + $0 (Gemini Lite через OpenRouter)

**Миграция завершена:** 03.03.2026 — MacBook Air 8GB → MacBook Pro M1 32GB
- Архив migration-to-macbook-pro.md сохранён в memory/

## Инструменты

### Token Analyzer CLI
- Расположение: `~/.openclaw/workspace/tools/token-analyzer/`
- Запуск: `source venv/bin/activate && python analyzer.py summary`
- Команды: `summary`, `by-agent`, `by-day`, `top-sessions`
- Текущая статистика: 507M токенов, $119, 35 сессий

### 2026-02-28 18:49
Тестовая запись — Этап 2 начат

### 2026-03-04 10:53
**Добавлено правило Proof of Work для всех агентов**

### 2026-03-04 16:47
**Миграция на Gemini 3.1 Flash Lite Preview**

Новая модель на OpenRouter: `google/gemini-3.1-flash-lite-preview`
- Pricing: $0.25/M input, $1.50/M output (дешевле в 2x!)
- Context: 66K

Обновлены агенты:
- quick-research: gemini-2.5-flash-lite → gemini-3.1-flash-lite-preview
- quick-coder: gemini-2.5-flash-lite → gemini-3.1-flash-lite-preview
- planner: gemini-2.5-flash-lite → gemini-3.1-flash-lite-preview

Алиас: Gemini-3.1-Lite

Источник: совет из канала "Вайб-кодинг" (vibecoding_tg)

Правило:
```
Never say 'done' or 'working on it' unless the action has actually started.
Every status update must include proof — a process ID, file path, URL, or command output.
No proof = didn't happen.
A false completion is worse than a delayed honest answer.
```

Обновлены файлы:
- `workspace/AGENTS.md` — секция "Proof of Work Rule" в Telegram Status Protocol
- `workspace-main-worker/AGENTS.md` — добавлено в CRITICAL RULES
- `workspace-quick-research/AGENTS.md` — добавлено в начало
- `workspace-quick-coder/AGENTS.md` — добавлено в начало
- `workspace-main-reviewer/AGENTS.md` — добавлено в начало
