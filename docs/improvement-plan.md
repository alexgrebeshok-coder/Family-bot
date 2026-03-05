# План улучшений OpenClaw (5 недель)

## Этап 1: Утренний дайджест (Неделя 1)
**Цель:** Расширить утренний audio briefing

### Задачи:
1. Добавить Reddit Digest — топ-3 поста из r/homeassistant, r/MacApps, r/productivity
2. Добавить YouTube Digest — новые видео от избранных каналов (настроить список)
3. Объединить с текущим audio briefing в один комплексный дайджест
4. Добавить текстовую версию в Telegram

### Навыки:
- Создать skill `reddit-digest` (web_fetch + summarize)
- Создать skill `youtube-digest` (RSS feed парсинг)
- Обновить audio-briefing скрипт

### Ресурсы:
- Reddit API (бесплатно, без ключа)
- YouTube RSS feeds (бесплатно)
- Время: 3-4 часа

### Результат:
Ежедневный дайджест в 07:30: аудио + текст в Telegram с погодой, новостями, Reddit, YouTube

---

## Этап 2: Second Brain + Memory Search (Неделя 2)
**Цель:** Улучшить запоминание и поиск

### Задачи:
1. Semantic Memory Search — векторный поиск по MEMORY.md и daily notes
2. Команда "/запомни X" — сохранять в MEMORY.md через Telegram
3. Автоматическое извлечение инсайтов из daily notes в MEMORY.md
4. Команда "/найди X" — семантический поиск по памяти

### Навыки:
- Использовать memory-core plugin (уже установлен)
- Создать skill `second-brain` с командами
- Добавить heartbeat task для обновления MEMORY.md

### Ресурсы:
- memory-core plugin (встроенный)
- embeddings через OpenRouter (gemini-lite, бесплатно)
- Время: 4-5 часов

### Результат:
Поиск по памяти + автоматическое запоминание через Telegram

---

## Этап 3: Personal CRM (Неделя 3)
**Цель:** Автоматическое отслеживание контактов

### Задачи:
1. Парсинг email для извлечения контактов (имя, email, контекст)
2. Парсинг calendar для встреч
3. База контактов в data/contacts.json
4. Команды: "/контакты", "/контакт [имя]", "/когда виделись [имя]"
5. Напоминания о необходимости связаться

### Навыки:
- gog skill (уже есть) для Gmail/Calendar
- Создать skill `personal-crm`
- Интеграция с heartbeat

### Ресурсы:
- gog CLI (уже установлен)
- Время: 5-6 часов

### Результат:
Автоматическая база контактов с историей взаимодействий

---

## Этап 4: Family Calendar & Household (Неделя 4)
**Цель:** Семейный календарь + household management

### Задачи:
1. Агрегация семейных календарей (Google Calendar каждого)
2. Morning briefing с событиями семьи на сегодня
3. Отслеживание household inventory (продукты, мелочи)
4. Команды: "/купить X", "/список покупок", "/календарь"
5. Шопинг-лист в общем доступе

### Навыки:
- gog skill для Google Calendar API
- Создать skill `household-manager`
- Интеграция с семейным ботом

### Ресурсы:
- Google Calendar API (бесплатно)
- Время: 6-7 часов

### Результат:
Единый семейный календарь + управление household через Telegram

---

## Этап 5: Autonomous Tasks & Self-Healing (Неделя 5)
**Цель:** Автономные задачи и самовосстановление

### Задачи:
1. Goal-Driven Tasks — ставить цели на ночь, получать результат утром
2. Self-Healing — мониторинг системы, автоисправление проблем
3. Weekly report — еженедельная сводка активности
4. Proactive suggestions — предложения по улучшению

### Навыки:
- Создать skill `autonomous-goals`
- Обновить heartbeat для self-healing
- Создать skill `weekly-report`

### Ресурсы:
- Существующие агенты (quick-research, main-worker)
- Cron jobs
- Время: 7-8 часов

### Результат:
Система работает автономно, сама исправляет проблемы, генерирует идеи

---

## Приоритизация (матрица польза/сложность):

| Этап | Польза | Сложность | Приоритет |
|------|--------|-----------|-----------|
| 1. Morning Digest | ⭐⭐⭐⭐ | ⭐⭐ | 🔴 Высокий |
| 2. Second Brain | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 🔴 Высокий |
| 3. Personal CRM | ⭐⭐⭐ | ⭐⭐⭐ | 🟡 Средний |
| 4. Family Calendar | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 🟡 Средний |
| 5. Autonomous | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 🟢 Низкий (финальный) |

---

## Ограничения (MacBook Air 8GB):

- Максимум 2 параллельных агента
- Не запускать council (5 агентов) без освобождения памяти
- Предпочитать quick-research/quick-coder (бесплатно)
- Использовать main-worker только для exec/write/edit

---

## Стоимость:

- ZAI Pro: $15/мес (main, main-worker, main-reviewer)
- OpenRouter Gemini Lite: $0 (quick-research, quick-coder, quick-writer, planner)
- Reddit/YouTube APIs: $0
- Google Calendar API: $0
- **Итого: $15/мес**

---

## Итого:

- 5 этапов по 1 неделе
- ~25-30 часов работы
- Результат: полноценный AI-ассистент для семьи с памятью, CRM, календарём и автономными задачами
