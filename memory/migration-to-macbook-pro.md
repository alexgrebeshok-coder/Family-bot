# Миграция OpenClaw: MacBook Air → MacBook Pro M1 32GB

**Дата обновления:** 02.03.2026 21:30
**Статус:** Готов к миграции
**Источник:** docs.openclaw.ai + исследование

---

## 📊 Сравнение

| Параметр | MacBook Air | MacBook Pro M1 |
|----------|-------------|----------------|
| Память | 8GB | 32GB (4x) |
| Параллельные агенты | 2 (max) | 16 (max) |
| Свободная память | ~60MB | Ожидается 10GB+ |

---

## ⚠️ Критичные находки исследования

### 1. Официальный гайд
https://docs.openclaw.ai/install/migrating

> "Copy the **entire** `$OPENCLAW_STATE_DIR` folder. `openclaw.json` is not enough."

### 2. Абсолютные пути (23 штуки!)
**Проблема:** В конфиге 23 абсолютных пути `/Users/aleksandrgrebeshok/`

**Решение:**
- Вариант A: То же имя пользователя на новом Mac → не нужно ничего менять
- Вариант B: Symlink `ln -s /Users/NEW_USER /Users/aleksandrgrebeshok`
- Вариант C: sed замена путей

### 3. LaunchAgent
**Не найден** в `~/Library/LaunchAgents/`. Gateway запускается через `openclaw gateway start`.

---

## ЭТАП 1: Подготовка MacBook Pro

### 1.1 Установка зависимостей
```bash
# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Node.js
brew install node@22

# Git
brew install git

# Whisper.cpp (для транскрибации голосовых)
brew install whisper-cpp

# OpenClaw
npm install -g openclaw
```

### 1.2 Создать того же пользователя (рекомендуется)
**ВАЖНО:** Если создать пользователя `aleksandrgrebeshok` — все пути будут работать без изменений!

Если другой пользователь — понадобится symlink или sed замена.

---

## ЭТАП 2: Бэкап MacBook Air

### 2.1 Остановить gateway
```bash
openclaw gateway stop
```

### 2.2 Полный бэкап state directory
```bash
cd ~

# Полный бэкап ~/.openclaw/ (2.6GB)
tar -czvf openclaw-state-backup.tgz .openclaw

# Проверить размер
ls -lh openclaw-state-backup.tgz
```

### 2.3 Экспорт cron
```bash
crontab -l > ~/crontab-backup.txt
cat ~/crontab-backup.txt
```

### 2.4 Сохранить в безопасное место
- Внешний диск / флешка
- AirDrop
- iCloud (медленно)

**⚠️ ВАЖНО:** Backup содержит секреты (API ключи). Не публиковать!

---

## ЭТАП 3: Перенос на MacBook Pro

### 3.1 Перенести архив
```bash
# Вариант A: AirDrop
# Перетащить openclaw-state-backup.tgz

# Вариант B: SCP (если в одной сети)
scp openclaw-state-backup.tgz user@macbook-pro.local:~/

# Вариант C: USB диск
cp openclaw-state-backup.tgz /Volumes/USB/
```

### 3.2 Распаковать
```bash
cd ~
tar -xzf openclaw-state-backup.tgz
```

### 3.3 Исправить пути (ЕСЛИ нужно!)
**Если пользователь ДРУГОЙ:**
```bash
# Заменить пути в конфиге
sed -i '' 's|/Users/aleksandrgrebeshok/|/Users/NEW_USERNAME/|g' ~/.openclaw/openclaw.json
sed -i '' 's|/Users/aleksandrgrebeshok/|/Users/NEW_USERNAME/|g' ~/.openclaw/mcp-servers.json

# ИЛИ создать symlink (проще)
sudo ln -s /Users/NEW_USERNAME /Users/aleksandrgrebeshok
```

**Если пользователь ТАКОЙ ЖЕ — ничего не делать!**

---

## ЭТАП 4: Конфигурация MacBook Pro

### 4.1 Doctor check
```bash
openclaw doctor
```

### 4.2 Запустить gateway
```bash
openclaw gateway start
```

### 4.3 Установить LaunchAgent (опционально)
```bash
openclaw gateway install
```

### 4.4 Восстановить cron
```bash
crontab ~/crontab-backup.txt
crontab -l
```

---

## ЭТАП 5: Тестирование

### 5.1 Базовая проверка
```bash
openclaw status
openclaw --version
```

### 5.2 Dashboard
Открыть http://localhost:18789

### 5.3 Telegram бот
- Отправить `/status` в Telegram
- Проверить inline buttons

### 5.4 API ключи
| Провайдер | Проверка |
|-----------|----------|
| ZAI | Отправить сообщение |
| OpenRouter | Запустить агента |
| Brave Search | web_search тест |
| Bright Data MCP | Проверить MCP сервер |

### 5.5 Семейный Бот
```bash
# Ручной тест
/Users/aleksandrgrebeshok/.openclaw/workspace/Проекты/Семейный\ Бот/run_daily.sh
```

### 5.6 Память и агенты
- Проверить `MEMORY.md` существует
- Запустить 5 параллельных агентов (тест памяти)

---

## ЭТАП 6: Откат (если что-то пошло не так)

### 6.1 На MacBook Air
```bash
# Если вернулись к старому Mac
crontab ~/crontab-backup.txt
openclaw gateway start
```

### 6.2 Типичные проблемы

| Проблема | Решение |
|----------|---------|
| Gateway не стартует | `openclaw doctor` |
| Токены не работают | Проверить `openclaw.json` |
| Cron не работает | `crontab -l`, проверить пути |
| MCP не запускается | Проверить пути в `mcp-servers.json` |
| Workspace не найден | Проверить symlink или sed |

---

## ЭТАП 7: Очистка MacBook Air (через неделю)

### 7.1 После успешной миграции

**Оставить как резерв (1-2 недели):**
- Gateway остановлен
- Cron отключен
- Backup сохранён

### 7.2 Полная очистка
```bash
# Остановить всё
openclaw gateway stop
openclaw gateway uninstall
crontab -r

# Удалить данные (ОСТОРОЖНО!)
rm -rf ~/.openclaw/
```

---

## 📋 Чек-лист миграции

### Перед миграцией
- [ ] MacBook Pro готов (Homebrew, Node, OpenClaw)
- [ ] Пользователь создан (желательно `aleksandrgrebeshok`)
- [ ] Время выделено (~1 час)
- [ ] Внешний диск / способ переноса готов

### На MacBook Air
- [ ] `openclaw gateway stop`
- [ ] `tar -czvf openclaw-state-backup.tgz .openclaw`
- [ ] `crontab -l > crontab-backup.txt`
- [ ] Backup проверен (размер ~2.6GB)
- [ ] Backup скопирован в безопасное место

### На MacBook Pro
- [ ] Архив перенесён
- [ ] `tar -xzf openclaw-state-backup.tgz`
- [ ] Пути исправлены (если нужно)
- [ ] `openclaw doctor` — OK
- [ ] `openclaw gateway start` — OK
- [ ] `openclaw status` — OK
- [ ] `crontab ~/crontab-backup.txt`
- [ ] Dashboard открывается (localhost:18789)
- [ ] Telegram бот отвечает
- [ ] Семейный Бот работает
- [ ] 5 параллельных агентов OK

### Через неделю
- [ ] MacBook Air очищен
- [ ] Gateway остановлен на старом Mac
- [ ] Cron удалён

---

## 🎯 После миграции

**Преимущества:**
- 16 параллельных агентов вместо 2
- Pipeline архитектура (Research → Execution → Review)
- Нет проблем с памятью
- 3x быстрее выполнение задач

**Первый тест:**
```bash
# Запустить 5 параллельных агентов
# Проверить память: vm_stat | perl ...
```

---

## 📝 Заметки

- Миграция простая — главное перенести ВЕСЬ `~/.openclaw/`
- Если тот же пользователь — пути не нужно менять
- Backup содержит секреты — хранить безопасно
- Семейный Бот можно временно запускать на обоих Mac
- MacBook Air оставить как резерв на неделю

---

## 🔗 Ресурсы

- **Официальный гайд:** https://docs.openclaw.ai/install/migrating
- **Doctor:** https://docs.openclaw.ai/gateway/doctor
- **FAQ:** https://docs.openclaw.ai/help/faq
- **Исследование:** `memory/migration-research.md`
