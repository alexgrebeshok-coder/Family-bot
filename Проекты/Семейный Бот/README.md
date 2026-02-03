# Семейный Бот (MVP)

Ежедневный пост в семейный Telegram‑чат/канал: погода (Сургут/Тюмень/Москва), праздники, короткие новости (Сургут/Москва).

## Стек
- Python
- Groq (LLM)
- .env для секретов

## Как запустить (план)
1. Заполнить `.env` (см. `.env.example`).
2. Установить зависимости: `pip install -r requirements.txt`.
3. Запуск генерации поста: `python src/generate_post.py` (будет добавлен).
4. Отправка в Telegram: `python src/send_post.py` (будет добавлен).

## Расписание
Cron уже настроен в OpenClaw на 07:30 (Asia/Yekaterinburg).
