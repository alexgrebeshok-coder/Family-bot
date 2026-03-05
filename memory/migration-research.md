# Исследование миграции OpenClaw на MacBook Pro

**Дата:** 2026-03-02
**Источник:** MacBook Air — Александр
**Цель:** Перенос конфигурации на MacBook Pro без потери данных

---

## 1. Критичные файлы — ОБЯЗАТЕЛЬНО перенести

### 1.1 Основная конфигурация
- `~/.openclaw/openclaw.json` — **КРИТИЧНО**
  - Содержит все API ключи (BRAVE_API_KEY, EXA_API_KEY, ZAI_API_KEY, OpenRouter)
  - Telegram bot token
  - Gateway auth token
  - Конфигурация всех агентов (23 агента!)
  - Model providers настройки

### 1.2 MCP сервера
- `~/.openclaw/mcp-servers.json` — **КРИТИЧНО**
  - Bright Data API token
  - Filesystem server path
  - Memory server config

### 1.3 Credentials (если есть)
- `~/.openclaw/credentials/` — **КРИТИЧНО**
  - OAuth токены
  - WhatsApp сессии
  - Другие авторизации

### 1.4 Сессии агентов
- `~/.openclaw/agents/<agentId>/sessions/` — **КРИТИЧНО**
  - История всех разговоров
  - Контекст сессий
  - Состояние агентов

### 1.5 Workspace файлы
- `~/.openclaw/workspace/` (или другие workspace директории)
  - `MEMORY.md` — долгосрочная память
  - `USER.md` — профиль пользователя
  - `SOUL.md`, `AGENTS.md`, `TOOLS.md` — настройки агента
  - `memory/*.md` — дневники

### 1.6 Skills
- `~/.openclaw/skills/` — пользовательские навыки
- `~/.openclaw/models/` — локальные модели (embeddings)

---

## 2. Опциональные файлы — можно НЕ переносить

### 2.1 Логи и кэш
- `~/.openclaw/logs/` — логи (займет место, не критично)
- `~/.openclaw/cache/` — кэш данных
- `*.log` файлы

### 2.2 Временные данные
- Временные sandbox файлы
- Cache файлы браузера (если есть)

### 2.3 Node modules (пересоберутся)
- Любые `node_modules/` внутри workspace

---

## 3. Проблемные места

### 3.1 Абсолютные пути в конфигурации ⚠️

**Найдено в `openclaw.json`:**

```json
// Workspace пути для 23 агентов
"workspace": "/Users/aleksandrgrebeshok/.openclaw/workspace"
"workspace": "/Users/aleksandrgrebeshok/.openclaw/workspace-coder"
// ... и еще 21 агент

// Embeddings модель
"modelPath": "/Users/aleksandrgrebeshok/.openclaw/models/embeddings/nomic-embed-text-v1.5.Q4_K_M.gguf"

// Sandbox roots
"workspaceRoot": "/Users/aleksandrgrebeshok/.openclaw/sandboxes"
```

**Решение:** После миграции нужно обновить пути на новое имя пользователя или использовать относительные пути.

### 3.2 Machine-specific данные

**Отсутствует LaunchAgent:**
- Файл `~/Library/LaunchAgents/com.openclaw.gateway.plist` не найден
- Вероятно, gateway запускается вручную или через другой механизм

**Telegram bot token:**
- Привязан к конкретному боту (должен работать на новом Mac)
- `allowFrom: ["1258992460"]` — whitelist пользователей

### 3.3 OAuth токены (если есть)
- OpenAI Codex OAuth
- Anthropic setup-token (если используется)
- Другие OAuth провайдеры

---

## 4. Пошаговый план миграции

### Подготовка на MacBook Air (старый Mac)

```bash
# 1. Остановить gateway
openclaw gateway stop

# 2. Создать backup
cd ~
tar -czf openclaw-state-backup.tgz .openclaw

# 3. Дополнительно заархивировать workspace (если вне .openclaw)
tar -czf openclaw-workspace.tgz .openclaw/workspace*

# 4. Проверить размер
ls -lh openclaw-*.tgz
```

### Перенос на MacBook Pro (новый Mac)

```bash
# 1. Установить OpenClaw (если еще не установлен)
brew install openclaw

# 2. Перенести архивы (через AirDrop, USB, или scp)
# Например, через scp:
# scp openclaw-state-backup.tgz user@new-mac:~/

# 3. Распаковать
cd ~
tar -xzf openclaw-state-backup.tgz

# 4. ИСПРАВИТЬ ПУТИ (критичный шаг!)
# Вариант A: Если имя пользователя такое же — ничего не делать
# Вариант B: Если имя пользователя другое — заменить пути:
# sed -i '' 's|/Users/aleksandrgrebeshok/|/Users/NEW_USERNAME/|g' ~/.openclaw/openclaw.json

# 5. Запустить doctor
openclaw doctor

# 6. Запустить gateway
openclaw gateway start

# 7. Проверить статус
openclaw status
```

### Проверка после миграции

```bash
# 1. Gateway работает
openclaw status

# 2. Telegram бот отвечает (проверить в Telegram)

# 3. Сессии на месте
# Открыть dashboard: http://localhost:18789

# 4. Workspace файлы существуют
ls -la ~/.openclaw/workspace/
cat ~/.openclaw/workspace/MEMORY.md

# 5. API ключи работают
# Попробовать отправить сообщение через Telegram
```

---

## 5. Риски и mitigations

### Риск 1: Потеря API ключей
**Severity:** КРИТИЧНЫЙ
**Mitigation:**
- Backup `openclaw.json` в безопасное место
- Не публиковать backup в публичные репозитории
- После миграции проверить все API ключи

### Риск 2: Абсолютные пути сломаются
**Severity:** ВЫСОКИЙ
**Mitigation:**
- Использовать sed для замены путей
- Или создать symlink: `ln -s /Users/NEW_USER /Users/aleksandrgrebeshok`
- После миграции проверить все workspace агентов

### Риск 3: OAuth токены истекли
**Severity:** СРЕДНИЙ
**Mitigation:**
- Проверить auth профили после миграции
- Переавторизоваться при необходимости (Codex, Anthropic)

### Риск 4: Telegram сессия потеряна
**Severity:** НИЗКИЙ (Telegram bot token должен работать)
**Mitigation:**
- Bot token не привязан к машине
- Проверить webhook/long polling после миграции

### Риск 5: Skills не работают
**Severity:** СРЕДНИЙ
**Mitigation:**
- Skills могут иметь hardcoded пути
- Проверить `~/.openclaw/skills/*/SKILL.md` на абсолютные пути
- Переустановить skills через clawhub если нужно

### Риск 6: MCP сервера не запускаются
**Severity:** СРЕДНИЙ
**Mitigation:**
- Проверить `mcp-servers.json` на абсолютные пути
- Bright Data токен должен работать
- Filesystem MCP может потребовать обновления пути

---

## 6. Официальная документация

### Источники
1. **Migration Guide:** https://docs.openclaw.ai/install/migrating
2. **FAQ:** https://docs.openclaw.ai/help/faq
3. **Doctor:** https://docs.openclaw.ai/gateway/doctor

### Ключевые цитаты из документации

> "Copy the **state directory** (`$OPENCLAW_STATE_DIR`, default: `~/.openclaw/`) — this includes config, auth, sessions, and channel state."

> "Copy your **workspace** (`~/.openclaw/workspace/` by default) — this includes your agent files (memory, prompts, etc.)."

> "`$OPENCLAW_STATE_DIR` contains secrets (API keys, OAuth tokens, WhatsApp creds). Treat backups like production secrets."

> "Always migrate the **entire** `$OPENCLAW_STATE_DIR` folder. `openclaw.json` is not enough."

---

## 7. Чек-лист перед миграцией

- [ ] Остановлен gateway (`openclaw gateway stop`)
- [ ] Создан backup `~/.openclaw/`
- [ ] Backup сохранен в безопасном месте
- [ ] Установлен OpenClaw на новом Mac
- [ ] Распакован backup на новом Mac
- [ ] Исправлены абсолютные пути (если нужно)
- [ ] Запущен `openclaw doctor`
- [ ] Запущен gateway (`openclaw gateway start`)
- [ ] Проверен `openclaw status`
- [ ] Проверен Telegram бот
- [ ] Проверен dashboard (http://localhost:18789)
- [ ] Проверены workspace файлы (MEMORY.md, USER.md)
- [ ] Протестированы API ключи (отправка сообщения)

---

## 8. Размеры директорий (оценка)

**Точный размер неизвестен** (exec заблокирован), но типичные размеры:
- `~/.openclaw/` — 500MB - 2GB (зависит от логов и моделей)
- `~/.openclaw/workspace/` — 1-50MB (текстовые файлы)
- `~/.openclaw/models/` — 100-500MB (embeddings модели)

**Рекомендация:** Создать backup и проверить размер перед переносом.

---

## 9. Альтернативные подходы

### Вариант A: Полный перенос (рекомендуется)
- Перенести весь `~/.openclaw/`
- Исправить пути
- Минимум ручной работы

### Вариант B: Выборочный перенос
- Перенести только `openclaw.json`, `mcp-servers.json`
- Перенести workspace файлы вручную
- Переавторизоваться во всех сервисах
- Потеря истории сессий

### Вариант C: Cloud sync (для workspace)
- Хранить workspace в Git репозитории
- Синхронизировать между машинами
- Не решает проблему с credentials

---

## 10. После миграции — что проверить

1. **Telegram:**
   - Бот отвечает на команды
   - Inline buttons работают
   - История сообщений на месте

2. **API ключи:**
   - ZAI API работает
   - OpenRouter работает
   - Brave Search работает
   - Exa Search работает
   - Bright Data MCP работает

3. **Agents:**
   - Все 23 агента доступны
   - Workspaces существуют
   - Model fallbacks работают

4. **Memory:**
   - `MEMORY.md` на месте
   - `memory/*.md` файлы существуют
   - Embeddings модель загружается

5. **Dashboard:**
   - Открывается http://localhost:18789
   - Auth token работает
   - Sessions видны

---

**Документ создан:** 2026-03-02 21:25 GMT+5
**Автор:** main-worker subagent
**Версия:** 1.0
