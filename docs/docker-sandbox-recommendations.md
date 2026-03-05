# Docker Sandbox Recommendations

## Текущий статус

```json
"sandbox": { "mode": "off" }  // для всех агентов
```

## Рекомендуемая конфигурация

### Main (оркестратор)
```json
{
  "id": "main",
  "sandbox": { "mode": "off" }  // оставить как есть
}
```
**Причина:** Main — оркестратор, нужен полный доступ к системе для управления другими агентами.

### Main-worker (исполнитель)
```json
{
  "id": "main-worker",
  "sandbox": { "mode": "all" }  // включить Docker
}
```
**Причина:** Выполняет exec команды, изоляция критична для безопасности.

### Quick-research, Quick-coder, Quick-writer
```json
{
  "id": "quick-research",
  "sandbox": { "mode": "all" }  // включить Docker
}
```
**Причина:** Web доступ, генерация кода — изоляция для безопасности.

### Main-reviewer
```json
{
  "id": "main-reviewer",
  "sandbox": { "mode": "off" }  // оставить
}
```
**Причина:** Только читает и анализирует, не выполняет команды.

---

## Как включить

### 1. Проверить Docker
```bash
docker --version
docker ps  # должен работать без sudo
```

### 2. Изменить конфиг
```bash
# Открыть конфиг
nano ~/.openclaw/openclaw.json

# Найти нужного агента и добавить:
"sandbox": { "mode": "all" }
```

### 3. Перезапустить gateway
```bash
openclaw gateway restart
```

### 4. Протестировать
```bash
# Запустить subagent с sandbox
openclaw agent run main-worker --task "echo test"
```

---

## ⚠️ Возможные проблемы

1. **Медленный запуск** — первый запуск контейнера занимает время
2. **Доступ к файлам** — нужно монтировать volumes
3. **Сеть** — может блокировать web запросы
4. **Текущие workflow** — могут сломаться

## Рекомендация

**Не включать сразу для всех агентов.** Начать с `main-worker`, протестировать, затем включать для остальных.

---

## Альтернатива: Partial sandbox

Если Docker слишком тяжёлый, можно использовать:

```json
{
  "sandbox": {
    "mode": "some",
    "exec": {
      "host": "sandbox"  // только exec команды в sandbox
    }
  }
}
```

---

Создано: 2026-03-05
Источник: OpenClaw best practices research
