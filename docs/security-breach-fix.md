# 🚨 КРИТИЧНО: Удаление секретов из Git

**Дата:** 2026-03-05 10:45
**Источник:** GitHub Security Alert

---

## Утечки найдены:

| Секрет | Файл | Commit |
|--------|------|--------|
| OpenRouter API Key | `Проекты/Семейный Бот/.env.example#L11` | 12652193 |
| Telegram Bot Token | `Проекты/Семейный Бот/.env.example#L26` | 12652123 |
| Telegram Bot Token | `memory/2026-03-03.md` (возможно) | 8789761 |

---

## ✅ Исправлено локально:

- `.env.example` — токены заменены на плейсхолдеры `YOUR_*`
- `memory/2026-03-03.md` — токенов не найдено

---

## ⚠️ Требуется действие:

### 1. Отозвать токены (КРИТИЧНО!)

**OpenRouter API Key:**
```
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
```
→ Зайти на https://openrouter.ai/keys
→ Удалить этот ключ
→ Создать новый

**Telegram Bot Token:**
```
8019020095:AAHakcUtfrT_RVaDcwVujHn9uszumMTXcng
```
→ Написать @BotFather в Telegram
→ `/mybots` → выбери бота → `/revoke` → подтвердить
→ Создать новый токен

---

### 2. Удалить из Git истории (ОПАСНО!)

**⚠️ Force push перепишет историю!**

```bash
# 1. Backup репозитория
cd ~/.openclaw/workspace
git clone https://github.com/alexgrebeshok-coder/Family-bot.git ../Family-bot-backup

# 2. Удалить .env.example из всей истории
git filter-repo --invert-paths --path "Проекты/Семейный Бот/.env.example" --force

# 3. Force push (ПЕРЕПИШЕТ ИСТОРИЮ!)
git remote add origin https://github.com/alexgrebeshok-coder/Family-bot.git
git push origin master --force

# 4. Уведомить GitHub
# GitHub автоматически пересканирует репозиторий
```

**Альтернатива (безопаснее):**
- Удалить репозиторий полностью
- Создать заново (без секретов)

---

### 3. Обновить локальные конфиги

После отзыва токенов обновить:

**~/.openclaw/agents/main/agent/models.json:**
```json
"openrouter": {
  "apiKey": "НОВЫЙ_КЛЮЧ"
}
```

**Семейный бот:**
```bash
# Создать .env файл с новыми токенами
cp "Проекты/Семейный Бот/.env.example" "Проекты/Семейный Бот/.env"
# Отредактировать .env с новыми токенами
```

---

## 📊 Статус:

- [ ] Отозвать OpenRouter API Key
- [ ] Отозвать Telegram Bot Token
- [ ] Удалить из git истории (или удалить репозиторий)
- [ ] Обновить локальные конфиги
- [ ] Протестировать бота с новыми токенами

---

**СРОЧНОСТЬ:** Высокая. Любой может использовать утёкшие токены.

**Автор:** Main agent
