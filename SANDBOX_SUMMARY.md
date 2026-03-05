# 🦞 Phase 3 Sandboxing — Сводка

## ✅ Что сделано

1. **Изучены docs** по sandboxing в OpenClaw
2. **Предложены безопасные параметры** для ограничения non-main агентов
3. **Подготовлена конфигурация** (main — read-only без overhead, workers — в Docker)
4. **Проверены существующие пути** (family bot, ops — не будут затронуты)
5. **Описаны риски и rollback**
6. **Подготовлены файлы** для применения изменений
7. **Нужен restart gateway** после применения

---

## 📊 Текущее состояние

### Main агент ✅
- **УЖЕ read-only**: только чтение, exec/process/write/edit запрещены
- **Без sandbox overhead**: mode: off
- **Workspace**: ~/.openclaw/workspace

### Non-main агенты ⚠️
- **БЕЗ sandboxing**: выполняются на хосте
- **Имеют доступ к exec/process/write/edit**: с allowlist + ask: on-miss
- **Workspace**: individual (~/.openclaw/workspace-*)

### Docker ✅
- Установлен и работает (v29.2.1)
- Контейнеры запущены

---

## 🎯 Предлагаемая конфигурация

```json
// defaults для всех агентов
"agents.defaults.sandbox": {
  "mode": "docker",
  "workspaceAccess": "agent",
  "workspaceRoot": "/Users/aleksandgreheshok/.openclaw/sandboxes"
}

// main — без sandboxing (текущее состояние)
"main.sandbox": {
  "mode": "off"
}

// non-main — в Docker (orch-*, coder, researcher, quick-*, ops-*)
"<agent-id>.sandbox": {
  "mode": "docker",
  "workspaceAccess": "agent",
  "workspaceRoot": "/Users/aleksandgreheshok/.openclaw/sandboxes"
}
```

---

## 📁 Подготовленные файлы

1. **`phase3_sandboxing_report.md`** — полный отчёт (рекомендуется читать)
2. **`phase3_sandboxing_proposal.md`** — детальное описание
3. **`openclaw_sandboxing_diff.md`** — diff изменений
4. **`apply_sandboxing.sh`** — скрипт для применения

---

## 🚀 Применение изменений

### Автоматическое (рекомендуется)
```bash
cd ~/.openclaw/workspace
./apply_sandboxing.sh
```

### Ручное
1. Редактировать `~/.openclaw/openclaw.json` (см. diff)
2. `openclaw gateway restart`

---

## ⚠️ Риски

| Риск | Митигация | Rollback |
|------|-----------|----------|
| Docker не работает | Проверка до применения | cp backup + restart |
| Performance overhead | Main без sandboxing | cp backup + restart |
| Volume mounts | Тест одного агента | cp backup + restart |
| Family bot / Ops | Main без sandboxing | cp backup + restart |

### Rollback (10 секунд)
```bash
cp ~/.openclaw/openclaw.json.backup-20260221-133512 ~/.openclaw/openclaw.json
openclaw gateway restart
```

---

## ✨ Преимущества

- ✅ Main остаётся read-only БЕЗ overhead
- ✅ Workers изолированы в Docker
- ✅ Workspace paths не меняются
- ✅ Family bot / Ops не затронуты
- ✅ Tool policy не меняется
- ✅ Rollback простой

---

## ❓ Нужен ли restart?

**ДА** — sandbox runtime инициализируется при старте gateway.

---

## 📝 Рекомендация

**Применить изменения** — безопасно, rollback простой, преимущества очевидны.

Если сомневаетесь:
1. Тест в `--profile test`
2. Или тест на одном агенте (quick-coder)

---

## 📚 Документация

- https://docs.openclaw.ai/cli/sandbox
- https://docs.openclaw.ai/gateway/security

---

**Готово к применению** ✅
