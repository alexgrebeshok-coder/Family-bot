#!/usr/bin/env python3
"""Family Telegram Bot (MVP)

Daily cron job:
- Fetch weather (Surgut, Tyumen, Moscow) via Open-Meteo
- Fetch holidays (simple local list)
- Fetch RSS news (1–2 sources)
- Ask Groq LLM to compose warm family post
- Send to Telegram channel/group
"""
from __future__ import annotations

import os
import sys
import json
import textwrap
from datetime import datetime
from typing import Dict, List, Tuple

import requests
import feedparser
from dotenv import load_dotenv

# -----------------------------
# Config & Constants
# -----------------------------
CITIES = {
    "Сургут": (61.25, 73.43),
    "Тюмень": (57.15, 65.53),
    "Москва": (55.75, 37.62),
}

DEFAULT_NEWS_LIMIT = 3
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

HOLIDAYS_FIXED = {
    "01-01": "Новый год",
    "01-07": "Рождество",
    "02-23": "День защитника Отечества",
    "03-08": "Международный женский день",
    "05-01": "Праздник Весны и Труда",
    "05-09": "День Победы",
    "06-12": "День России",
    "11-04": "День народного единства",
}


# -----------------------------
# Utilities
# -----------------------------

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def http_get(url: str, params: dict | None = None, timeout: int = 20) -> dict:
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


# -----------------------------
# Weather
# -----------------------------

def get_weather() -> Dict[str, str]:
    """Return weather summary per city.

    Uses Open-Meteo current weather and hourly precipitation probability.
    """
    result: Dict[str, str] = {}

    for city, (lat, lon) in CITIES.items():
        try:
            data = http_get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,wind_speed_10m",
                    "hourly": "precipitation_probability",
                    "timezone": "Europe/Moscow",
                },
            )
            cur = data.get("current", {})
            temp = cur.get("temperature_2m")
            feels = cur.get("apparent_temperature")
            wind = cur.get("wind_speed_10m")

            # Take max precipitation probability for next 6 hours if available
            precip = ""
            hourly = data.get("hourly", {})
            probs = hourly.get("precipitation_probability", [])
            if probs:
                max_next = max(probs[:6])
                precip = f", осадки до {max_next}%"

            result[city] = (
                f"{temp:+.0f}°C, ощущается как {feels:+.0f}°C, "
                f"ветер {wind:.0f} м/с{precip}"
            )
        except Exception as e:
            result[city] = f"нет данных о погоде ({e.__class__.__name__})"

    return result


# -----------------------------
# Holidays
# -----------------------------

def get_holidays(today: datetime) -> str:
    """Return a holiday string or 'Сегодня обычный день'."""
    key = today.strftime("%m-%d")
    holiday = HOLIDAYS_FIXED.get(key)
    return holiday or "Сегодня обычный день"


# -----------------------------
# News (RSS)
# -----------------------------

def get_news(rss_urls: List[str], limit: int = DEFAULT_NEWS_LIMIT) -> List[str]:
    items: List[str] = []
    for url in rss_urls:
        if not url:
            continue
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]:
                title = (entry.get("title") or "").strip()
                if title:
                    items.append(title)
        except Exception:
            continue

    # de-duplicate while preserving order
    seen = set()
    deduped = []
    for t in items:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped[:limit]


# -----------------------------
# LLM (Groq)
# -----------------------------

def build_prompt(weather: Dict[str, str], holidays: str, news: List[str]) -> str:
    weather_lines = "\n".join([f"- {city}: {desc}" for city, desc in weather.items()])
    news_lines = "\n".join([f"- {n}" for n in news]) if news else "- Сегодня без заметных местных новостей"

    return textwrap.dedent(
        f"""
        Ты — дружелюбный семейный помощник. Сделай краткую сводку дня на основе данных.
        Тон: тёплый, заботливый. Используй эмодзи. Не пиши ничего лишнего, только текст поста.

        Формат:
        1) Приветствие + эмодзи
        2) Погода (буллеты)
        3) Праздники (1 строка)
        4) Новости (1–3 буллета)
        5) Короткая фраза на сегодня (1 строка, опционально)

        Данные:
        Погода:
        {weather_lines}

        Праздники:
        {holidays}

        Новости:
        {news_lines}
        """
    ).strip()


def generate_post(prompt: str, api_key: str, model: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://openclaw.ai",
        "X-Title": "Family Bot MVP",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6,
        "max_tokens": 500,
    }

    r = requests.post(OPENROUTER_API_URL, headers=headers, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


# -----------------------------
# Telegram
# -----------------------------

def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()


# -----------------------------
# Main
# -----------------------------

def main() -> int:
    load_dotenv()

    try:
        tg_token = require_env("TELEGRAM_BOT_TOKEN")
        tg_chat = require_env("TELEGRAM_CHAT_ID")
        openrouter_key = require_env("OPENROUTER_API_KEY")
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    model = os.getenv("OPENROUTER_MODEL", "z-ai/glm-4.5-air:free")

    rss_surgut = os.getenv("RSS_SURGUT", "").strip()
    rss_moscow = os.getenv("RSS_MOSCOW", "").strip()
    rss_urls = [rss_surgut, rss_moscow]

    weather = get_weather()
    holidays = get_holidays(datetime.now())
    news = get_news(rss_urls)

    prompt = build_prompt(weather, holidays, news)
    post = generate_post(prompt, openrouter_key, model)

    send_telegram(tg_token, tg_chat, post)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
