# OpenClaw Watchdog - Implementation Report

## TL;DR - Quick Reference

```bash
# Start/Stop watchdog (LaunchAgent)
launchctl load ~/Library/LaunchAgents/com.openclaw.watchdog.plist   # Start
launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog.plist  # Stop

# Check status
launchctl list | grep openclaw    # Watchdog status
openclaw gateway status           # Gateway status

# View logs
tail -f /Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_watchdog.log

# Manual run
/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.sh

# Rollback (git)
cd /Users/aleksandrgrebeshok/.openclaw/workspace && git reset --hard HEAD~1
```

## Что создано/изменено

### 1. Watchdog скрипт
**Файл:** `/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.sh`

**Функционал:**
- Проверяет статус OpenClaw Gateway через `openclaw gateway status`
- При обнаружении сбоя выполняет `openclaw gateway restart`
- Повторно проверяет статус после backoff задержки
- Ведёт подробное логирование в `/Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_watchdog.log`
- Использует lockfile для предотвращения множественных запусков
- Реализует backoff-ретраи: 5s → 15s → 30s → 60s → (повторение цикла)
- Ограничивает количество попыток: максимум 10 попыток перед выходом с кодом 1
- Поддерживает уведомления через переменную `WATCHDOG_NOTIFY_CMD`

**Почему 10 попыток вместо бесконечных:**
- Избегает бесконечных циклов в одном процессе (защита от зависаний)
- Позволяет LaunchAgent перезапустить watchdog с чистым состоянием
- При постоянной проблеме watchdog не будет бесконечно потреблять ресурсы
- Если все 10 попыток неудачны, это указывает на серьёзную системную проблему, требующую ручного вмешательства

### 2. LaunchAgent
**Файл:** `~/Library/LaunchAgents/com.openclaw.watchdog.plist`

**Конфигурация:**
- `RunAtLoad`: запускается сразу после загрузки
- `KeepAlive`: перезапускается при выходе с ненулевым кодом
- `StartInterval`: 60 секунд (периодическая проверка как резерв)
- `StandardOutPath`: лог stdout в `logs/openclaw_watchdog_stdout.log`
- `StandardErrorPath`: лог stderr в `logs/openclaw_watchdog_stderr.log`
- `PATH`: включает `/opt/homebrew/bin` для команды `openclaw`

### 3. Git коммит
**Коммит:** `4050fd7` - "feat: add OpenClaw watchdog script"

---

## Используемые команды

### Управление LaunchAgent

```bash
# Загрузить LaunchAgent
launchctl load ~/Library/LaunchAgents/com.openclaw.watchdog.plist

# Остановить LaunchAgent
launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog.plist

# Проверить статус
launchctl list | grep openclaw

# Принудительная выгрузка (если нужно)
launchctl bootout gui/$UID/com.openclaw.watchdog
```

### Ручное тестирование скрипта

```bash
# Запустить watchdog вручную
/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.sh

# Проверить логи
tail -f /Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_watchdog.log
```

### Симуляция сбоя gateway для тестирования

```bash
# Остановить gateway
openclaw gateway stop

# Запустить watchdog вручную и наблюдать лог
/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.sh
```

---

## Как откатить изменения

### 1. Откатить git изменения

```bash
cd /Users/aleksandrgrebeshok/.openclaw/workspace

# Удалить последний коммит (но сохранить изменения)
git reset HEAD~1

# ИЛИ удалить коммит и изменения полностью
git reset --hard HEAD~1

# Если уже отправлено в удалённый репозиторий
git revert HEAD
```

### 2. Удалить LaunchAgent

```bash
# Остановить и выгрузить
launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog.plist

# Удалить файл plist
rm ~/Library/LaunchAgents/com.openclaw.watchdog.plist

# Очистить системный кэш launchctl (если нужно)
launchctl kickstart -k gui/$(id -u)/com.openclaw.watchdog
```

### 3. Удалить файлы и логи

```bash
# Удалить скрипт
rm /Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.sh

# Удалить README (по желанию)
rm /Users/aleksandrgrebeshok/.openclaw/workspace/ops/README_WATCHDOG.md

# Удалить логи (по желанию)
rm /Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_watchdog.log
rm /Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_watchdog_stdout.log
rm /Users/aleksandrgrebeshok/.openclaw/workspace/logs/openclaw_watchdog_stderr.log

# Удалить lockfile
rm /Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.lock
```

---

## Рекомендации по использованию

### Для продакшена

1. **Оставьте LaunchAgent активным** - watchdog будет поддерживать gateway в живом состоянии
2. **Периодически проверяйте логи** - особенно если gateway был неожиданно перезапущен
3. **Мониторинг** - включите уведомления через `WATCHDOG_NOTIFY_CMD` (см. ниже)

### Уведомления

Watchdog поддерживает уведомления через переменную `WATCHDOG_NOTIFY_CMD`. При включении вы будете получать уведомления о:
- Успешном рестарте gateway
- Исчерпании всех попыток восстановления

**Включение уведомлений:**

Редактируйте `/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.sh`:

```bash
# Замените пустую строку на команду для уведомлений:
WATCHDOG_NOTIFY_CMD="terminal-notifier -message"

# Или используйте osascript для системных уведомлений:
WATCHDOG_NOTIFY_CMD="osascript -e 'display notification \"$message\" with title \"OpenClaw Watchdog\"'"
```

**Примеры команд уведомлений:**

```bash
# macOS terminal-notifier (установка: brew install terminal-notifier)
WATCHDOG_NOTIFY_CMD="terminal-notifier -message"

# macOS встроенные уведомления (без установки)
WATCHDOG_NOTIFY_CMD="osascript -e 'display notification \"$message\" with title \"OpenClaw Watchdog\"'"

# Локальный webhook (для интеграции с другими системами)
WATCHDOG_NOTIFY_CMD="curl -s -X POST -d 'message=$message' http://localhost:8080/webhook"

# Пользовательский скрипт
WATCHDOG_NOTIFY_CMD="/path/to/notify.sh"
```

**Перезапуск watchdog после изменений:**

```bash
# Перезагрузить LaunchAgent для применения изменений
launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.watchdog.plist
```

### Для разработки

1. **Останавливайте watchdog** при отладке gateway, чтобы избежать конфликтов
2. **Используйте ручной запуск** для тестирования новых функций
3. **Очищайте lockfile** если watchdog завис: `rm ops/openclaw_watchdog.lock`

---

## Тестирование выполнено

✅ Скрипт создан и сделан исполняемым
✅ LaunchAgent загружен и проверен
✅ PATH исправлен для команды `openclaw` (добавлен `/opt/homebrew/bin`)
✅ Watchdog успешно перезапущен после изменения конфигурации
✅ Логирование работает корректно
✅ Git commit создан

---

## Возможные проблемы и решения

### Проблема: "openclaw: command not found"
**Решение:** Убедитесь, что `/opt/homebrew/bin` добавлен в `PATH` в LaunchAgent plist

### Проблема: Watchdog не перезапускает gateway
**Решение:** Проверьте логи в `logs/openclaw_watchdog.log` для диагностики

### Проблема: Lockfile не удаляется при аварийном завершении
**Решение:** Watchdog автоматически удаляет stale lockfiles при запуске

### Проблема: Множественные экземпляры watchdog
**Решение:** Lockfile предотвращает множественные запуски; проверьте `ps aux | grep openclaw_watchdog`
