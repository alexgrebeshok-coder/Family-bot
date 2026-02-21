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

Watchdog поддерживает уведомления через переменную `WATCHDOG_NOTIFY_CMD` и скрипт `watchdog_notify.sh`.

**Текущая конфигурация (Telegram DM):**

- Уведомления включены по умолчанию
- Сообщения отправляются в Telegram (target: 1258992460)
- Скрипт: `/Users/aleksandrgrebeshok/.openclaw/workspace/ops/watchdog_notify.sh`

**Изменение канала или получателя:**

Редактируйте `/Users/aleksandrgrebeshok/.openclaw/workspace/ops/watchdog_notify.sh`:

```bash
# Измените target на нужный Telegram ID
openclaw message send --channel telegram --target 1258992460 --message "$MESSAGE"
#                                                  ^^^^^^^^^^ Ваш Telegram ID
```

**Отключение уведомлений:**

В `/Users/aleksandrgrebeshok/.openclaw/workspace/ops/openclaw_watchdog.sh` очистите переменную:

```bash
# Очистить для отключения:
WATCHDOG_NOTIFY_CMD=""
```

**Перезапуск watchdog после изменений:**

```bash
# Перезагрузить LaunchAgent
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

---

## Прозрачность и Уведомления

Watchdog обеспечивает максимальную прозрачность через систему уведомлений о всех ключевых событиях.

### Уведомляемые события

| Событие | Описание | Пример сообщения |
|---------|----------|------------------|
| **Старт watchdog** | Запуск watchdog (каждый раз при активации LaunchAgent) | `OpenClaw Watchdog: started (PID: 12345), monitoring gateway...` |
| **Gateway down detected** | Обнаружен сбой gateway | `OpenClaw Watchdog: gateway DOWN detected, starting recovery...` |
| **Попытка рестарта** | Каждая попытка перезапуска gateway | `OpenClaw Watchdog: restart attempt 1/10` |
| **Рестарт успешен** | Gateway восстановлен после сбоя | `OpenClaw Watchdog: gateway recovered after 1 attempt(s)` |
| **Фатал после N попыток** | Не удалось восстановить gateway за MAX_ATTEMPTS | `OpenClaw Watchdog: FATAL - failed to recover gateway after 10 attempts` |
| **Heartbeat** | Периодическое подтверждение работы (раз в 6 часов) | `OpenClaw Watchdog heartbeat: gateway alive, monitoring active (last check: 2026-02-21 09:43:00)` |

### Heartbeat (Периодические подтверждения)

**Интервал:** Каждые 6 часов (настраивается через `HEARTBEAT_HOURS`)

**Файл состояния:** `/Users/aleksandrgrebeshok/.openclaw/workspace/ops/watchdog_heartbeat.ts`

Содержит epoch timestamp последнего отправленного heartbeat для предотвращения спама.

**Логика:**
- Watchdog проверяет timestamp при каждом запуске
- Если прошло ≥ `HEARTBEAT_HOURS` часов → отправляет heartbeat
- Обновляет timestamp после отправки (даже если подавлен quiet hours)

### Тихие часы (Quiet Hours)

**По умолчанию:** 19:00–07:00 (Asia/Yekaterinburg)

**Правило:**
- **Heartbeat подавляется** в тихие часы
- **Критические события (старт, down, restart attempts, fatal) — всегда отправляются**

**Переменные в `openclaw_watchdog.sh`:**
```bash
QUIET_HEARTBEAT_ONLY=true     # Подавлять только heartbeat (критические события всегда)
QUIET_START=19                # Начало тихих часов (19:00)
QUIET_END=7                   # Конец тихих часов (07:00)
HEARTBEAT_HOURS=6             # Интервал heartbeat (часы)
TIMEZONE="Asia/Yekaterinburg" # Часовой пояс для расчёта
```

### Настройка уровня тишины

#### 1. Отключить heartbeat (только критические события)

В `openclaw_watchdog.sh`:
```bash
# Увеличьте интервал heartbeat до экстремально большого значения
HEARTBEAT_HOURS=99999
```

#### 2. Полная тишина (все уведомления отключены)

В `openclaw_watchdog.sh`:
```bash
# Очистите переменную notification команды
WATCHDOG_NOTIFY_CMD=""
```

ИЛИ создайте флаг `QUIET_ALL=true` в начале скрипта:
```bash
QUIET_ALL=true  # Полная тишина (все уведомления отключены)
```

И измените функцию `notify()`:
```bash
notify() {
    local message="$*"
    # Полная тишина
    if [ "${QUIET_ALL}" = "true" ]; then
        log_info "NOTIFY (SUPPRESSED): ${message}"
        return 0
    fi
    # ... остальной код
}
```

#### 3. Изменить тихие часы

```bash
# Пример: тихие часы с 22:00 до 06:00
QUIET_START=22
QUIET_END=6
```

```bash
# Пример: отключить тихие часы (всегда отправлять heartbeat)
QUIET_START=0
QUIET_END=0  # Специальное значение: без тихих часов
```

#### 4. Изменить интервал heartbeat

```bash
# Каждые 12 часов вместо 6
HEARTBEAT_HOURS=12

# Каждый час (только для отладки!)
HEARTBEAT_HOURS=1
```

### Перезапуск после изменений

После любых изменений в `openclaw_watchdog.sh`:

```bash
# Перезагрузить LaunchAgent
launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.watchdog.plist

# Проверить статус
launchctl list | grep openclaw
```
