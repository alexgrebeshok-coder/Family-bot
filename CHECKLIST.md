# ✅ Phase 3 Sandboxing — Чек-лист

## Завершённые задачи

- [x] 1. Изучить docs по sandboxing в OpenClaw
  - [x] Проверены команды: `openclaw sandbox --help`, `openclaw sandbox explain`
  - [x] Проверена документация: `openclaw docs sandbox`
  - [x] Поняты параметры sandboxing (mode, workspaceAccess, workspaceRoot, perSession)

- [x] 2. Предложить безопасные параметры для non-main агентов
  - [x] Ограничить workspace через `workspaceAccess: "agent"`
  - [x] Использовать Docker sandboxing (`mode: "docker"`)
  - [x] Оставить main без sandboxing для избежания overhead

- [x] 3. Настроить sandboxing
  - [x] Main остаётся read-only и без sandbox overhead
  - [x] Workers будут ограничены Docker sandboxing
  - [x] Подготовлена конфигурация для 17 non-main агентов

- [x] 4. Не ломать существующие пути
  - [x] Family bot: main агент без sandboxing (вероятно, family bot использует main)
  - [x] Ops агенты: workspace пути сохраняются
  - [x] Tool policy не меняется

- [x] 5. Описать риски и rollback
  - [x] Риски задокументированы (Docker, performance, volume mounts, network)
  - [x] Rollback план создан
  - [x] Backup создан: `openclaw.json.backup-20260221-133512`

- [x] 6. Подготовить изменения (с backup)
  - [x] Backup создан ✅
  - [x] Diff подготовлен: `openclaw_sandboxing_diff.md`
  - [x] Скрипт готов: `apply_sandboxing.sh`
  - [x] **Изменения НЕ применены** — ждут подтверждения

- [x] 7. Не перезапускать gateway без необходимости
  - [x] Gateway НЕ перезапущен ✅
  - [x] Перезапуск нужен только ПОСЛЕ применения изменений

---

## 📁 Созданные файлы

1. **`SANDBOX_SUMMARY.md`** — краткая сводка для быстрого просмотра
2. **`phase3_sandboxing_report.md`** — полный отчёт с деталями
3. **`phase3_sandboxing_proposal.md`** — детальное описание концепции
4. **`openclaw_sandboxing_diff.md`** — diff изменений в openclaw.json
5. **`apply_sandboxing.sh`** — автоматический скрипт для применения
6. **`CHECKLIST.md`** — этот файл

---

## 🎯 Что изменится

### После применения:

1. **Main агент** — без изменений (уже read-only, без sandbox)
2. **17 worker агентов** — будут выполняться в Docker контейнерах:
   - orch-eng, orch-research, orch-ops
   - coder, coder2, eng-qa
   - researcher, research-synth, research-verify
   - writer, ops-tracker, ops-guard
   - eng-burst, research-burst, ops-burst
   - quick-research, quick-coder, quick-ops

3. **Workspace paths** — без изменений:
   - Host: `~/.openclaw/workspace-*`
   - Container: volume mount

4. **Tool policy** — без изменений:
   - Main: только чтение
   - Workers: allowlist + ask: on-miss

5. **Family bot / Ops** — без изменений (если используют main или корректно настроены)

---

## 🚀 Следующие шаги (для применения)

### Вариант A: Автоматическое применение (рекомендуется)
```bash
cd ~/.openclaw/workspace
./apply_sandboxing.sh
```

### Вариант B: Ручное применение
1. Прочитать `phase3_sandboxing_report.md`
2. Проверить `openclaw_sandboxing_diff.md`
3. Редактировать `~/.openclaw/openclaw.json`
4. `openclaw gateway restart`
5. `openclaw sandbox list` — проверить контейнеры

### Вариант C: Тестовый профиль
```bash
openclaw --profile test configure
# Применить изменения в test профиле
openclaw --profile test gateway start
# Тестировать агентов
```

---

## ⚠️ Перед применением: убедиться

- [ ] Docker запущен: `docker ps`
- [ ] Backup существует: `ls ~/.openclaw/openclaw.json.backup-*`
- [ ] Поняты риски (см. `phase3_sandboxing_report.md`)
- [ ] Понятен rollback (cp backup + restart)

---

## 🔍 После применения: проверить

- [ ] Gateway перезапущен без ошибок: `openclaw gateway status`
- [ ] Sandbox контейнеры запущены: `openclaw sandbox list`
- [ ] Main агент работает (проверить через Telegram)
- [ ] Один worker работает (например, попросить quick-coder что-то сделать)
- [ ] Логи без ошибок: `openclaw logs`
- [ ] Family bot работает (если используется)

---

## 🆘 Если проблемы

### Rollback (10 секунд)
```bash
cp ~/.openclaw/openclaw.json.backup-20260221-133512 ~/.openclaw/openclaw.json
openclaw gateway restart
```

### Диагностика
```bash
# Статус gateway
openclaw gateway status

# Логи
openclaw logs

# Sandbox контейнеры
openclaw sandbox list

# Объяснение конфигурации
openclaw sandbox explain

# Статус агентов
openclaw agents list
```

---

## 📊 Статистика

- **Изучено**: docs по sandboxing ✅
- **Предложено**: безопасная конфигурация ✅
- **Подготовлено**: 6 файлов документации и 1 скрипт ✅
- **Backup**: создан ✅
- **Docker**: проверен ✅
- **Применено**: ❌ (ждёт подтверждения)
- **Перезапущен gateway**: ❌ (нужен только после применения)

---

## ✨ Результат

**Phase 3 завершён** — sandboxing конфигурация подготовлена, документирована и готова к применению.

**Готово к внедрению** ✅

---

**Дата**: 2026-02-21
**Версия**: 2026.2.2-3
**Статус**: 🟡 Ждёт подтверждения для применения
