# MEMORY.md

## Ключевое (кратко)
- Проект: семейный Telegram‑бот (Python) в /Users/aleksandrgrebeshok/.openclaw/workspace/Проекты/Семейный Бот/
- LLM: OpenRouter (z-ai/glm-4.5-air:free). Погода: Open‑Meteo (Сургут/Тюмень/Москва). Новости: RSS (siapress.ru, interfax.ru)
- Расписание: ежедневный автозапуск в 07:30 Asia/Yekaterinberg через local cron + run_daily.sh
- Чат для постинга: супергруппа «Семья», chat_id = -1003880864767
- Правило: входящие аудио/voice по умолчанию расшифровывать через whisper‑cpp (whisper‑cli)
- **OpenClaw: 2026.3.2** (обновлено 05.03.2026)

## Архитектура агентов (обновлено 24.02.2026)

### Команда (7 агентов):

| Агент | Модель | Провайдер | Роль |
|-------|--------|-----------|------|
| **main** | glm-5 | ZAI Pro ($15) | Оркестратор, общение с пользователем |
| **main-worker** | glm-4.7 | ZAI | Исполнитель (exec, write, edit) |
| **quick-research** | gemini-3.1-flash-lite-preview | OpenRouter ($0) | Research, web поиск |
| **quick-coder** | gemini-3.1-flash-lite-preview | OpenRouter ($0) | Генерация кода |
| **quick-writer** | gemini-3.1-flash-lite-preview | OpenRouter ($0) | Тексты, документация |
| **planner** | gemini-3.1-flash-lite-preview | OpenRouter ($0) | Планирование задач |
| **main-reviewer** | glm-4.7-flash | ZAI | Критика, проверка качества |

### Результаты тестов параллельных агентов:

**Тест 24.02.2026:**
| Провайдер | Модель | 1 агент | 2 параллельно | Скорость |
|-----------|--------|---------|---------------|----------|
| **ZAI Pro** | glm-4.7-flash | ✅ | ✅ 1/2 | 42с |
| **OpenRouter** | gemini-2.5-flash-lite | ✅ | ✅ 2/2 | 21с |
| **OpenRouter free** | qwen3, deepseek | ❌ timeout | ❌ | — |

**Тест 05.03.2026 (Gemini 3.1 vs 2.5):**
| Model | Avg Time | Errors | Вывод |
|-------|----------|--------|-------|
| gemini-2.5-flash-lite | 5.02s | 0 | Baseline |
| gemini-3.1-flash-lite-preview | **1.43s** | 0 | **в 3.5x быстрее** ✅ |

→ Мигрировали на Gemini 3.1 Lite для всех subagents

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

### 2026-03-05 10:15
**Обновление OpenClaw 2026.3.2 + тест Gemini 3.1**

**OpenClaw обновлён:** 2026.3.1 → 2026.3.2
- Новые фичи: sessions_spawn attachments, PDF tool, security hardening
- Config valid, Gateway running ✅

**Тест Gemini 3.1 vs 2.5:**
- Скрипт: `~/.openclaw/workspace/tools/test_gemini_models.sh`
- Результат: Gemini 3.1 в 3.5x быстрее (1.43s vs 5.02s avg)
- Решение: оставить Gemini 3.1 Lite для всех subagents

**Security improvements:**
- `chmod 600 ~/.openclaw/openclaw.json` ✅
- Git backup: 53 файла, готово к push

### 2026-03-04 16:47
**Миграция на Gemini 3.1 Flash Lite Preview**

Новая модель: `google/gemini-3.1-flash-lite-preview`
- Pricing: $0.25/M input, $1.50/M output (дешевле в 2x!)
- Context: 66K

Алиас: Gemini-3.1-Lite
Источник: канал "Вайб-кодинг" (vibecoding_tg)

### 2026-03-04 10:53
**Добавлено правило Proof of Work для всех агентов**

```
Never say 'done' or 'working on it' unless the action has actually started.
Every status update must include proof — process ID, file path, URL, or command output.
No proof = didn't happen.
```
