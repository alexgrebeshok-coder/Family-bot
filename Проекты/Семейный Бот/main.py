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
import html
import re
import time
from pathlib import Path
from datetime import datetime, date, timedelta
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

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
ZAI_API_BASE_DEFAULT = "https://api.z.ai/api/paas/v4"

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

DEFAULT_NEWS_LIMIT = 2
DEFAULT_NEWS_TITLE_MAX = 90
DEFAULT_MAX_POST_CHARS = 900
DEFAULT_MAX_POST_LINES = 8
DEFAULT_ORTHODOX_ICAL_URL = "https://azbyka.ru/days/ics/calendar.ics"
DEFAULT_ORTHODOX_ICAL_PATH = "data/orthodox.ics"
DEFAULT_TRADITIONS_PATH = "data/traditional_holidays.json"
DEFAULT_HISTORY_PATH = "data/historical_events.json"
DEFAULT_ORTHODOX_ALLOW_DOWNLOAD = 0

ENCOURAGING_PHRASES = [
    "Пусть день будет спокойным 🙂",
    "Хорошего дня и тепла в доме 💛",
    "Пусть всё получится сегодня! ✨",
    "Берегите себя и близких 🤍",
]

MASLENITSA_DAYS = [
    ("Понедельник", "Встреча", "первые блины"),
    ("Вторник", "Заигрыши", "прогулки и игры"),
    ("Среда", "Лакомка", "угощения и блины"),
    ("Четверг", "Разгуляй", "гулянья и веселье"),
    ("Пятница", "Тёщины вечерки", "блины для тёщи"),
    ("Суббота", "Золовкины посиделки", "семейные посиделки"),
    ("Воскресенье", "Прощённое воскресенье", "попросить прощения"),
]

ORTHODOX_KEYWORDS = [
    "пасха",
    "воскресение христово",
    "рождество христово",
    "крещение",
    "богоявление",
    "сретение",
    "благовещение",
    "вход господень",
    "вознесение",
    "троица",
    "пятидесятниц",
    "преображение",
    "успение",
    "покров",
    "воздвижение",
    "рождество пресвятой богородицы",
    "введение во храм",
]

NEGATIVE_KEYWORDS = [
    "погиб",
    "смерт",
    "дтп",
    "убий",
    "катастроф",
    "взрыв",
    "пожар",
    "трагед",
    "авари",
    "криминал",
    "жертв",
    "ранен",
    "войн",
    "обстрел",
    "скончал",
    "умер",
    "теракт",
    "крах",
]


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


def get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def shorten_text(text: str, max_len: int) -> str:
    cleaned = normalize_space(text)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def pick_encouraging_phrase(today: date) -> str:
    idx = today.toordinal() % len(ENCOURAGING_PHRASES)
    return ENCOURAGING_PHRASES[idx]


def format_weather_inline(weather: Dict[str, str]) -> str:
    parts = [f"{city}: {desc}" for city, desc in weather.items()]
    return " / ".join(parts)


def orthodox_easter(year: int) -> date:
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    julian = date(year, month, day)
    delta = year // 100 - year // 400 - 2
    return julian + timedelta(days=delta)


def maslenitsa_info(today: date) -> str:
    easter = orthodox_easter(today.year)
    great_lent_start = easter - timedelta(days=48)
    maslenitsa_start = great_lent_start - timedelta(days=7)
    maslenitsa_end = great_lent_start - timedelta(days=1)

    if maslenitsa_start <= today <= maslenitsa_end:
        idx = (today - maslenitsa_start).days
        day_name, title, note = MASLENITSA_DAYS[idx]
        extra = " С понедельника Великий пост." if idx >= 4 else ""
        return f"Масленица — {title}: {note}.{extra}".strip()

    if today == great_lent_start:
        return "Начался Великий пост."
    days_to_lent = (great_lent_start - today).days
    if 0 < days_to_lent <= 3:
        return f"С {great_lent_start.strftime('%d.%m')} начнётся Великий пост."

    return ""


def load_traditional_holidays(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def get_traditional_today(today: date, path: Path) -> str:
    key = today.strftime("%m-%d")
    for item in load_traditional_holidays(path):
        if item.get("date") == key:
            name = item.get("name") or ""
            note = item.get("note") or ""
            if note:
                return f"{name}: {note}"
            return name
    return ""


def get_traditions(today: date, path: Path) -> str:
    maslenitsa = maslenitsa_info(today)
    if maslenitsa:
        return maslenitsa
    fixed = get_traditional_today(today, path)
    if fixed:
        return fixed
    return ""


def load_historical_events(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def get_historical_event(today: date, path: Path) -> str:
    key = today.strftime("%m-%d")
    for item in load_historical_events(path):
        if item.get("date") == key:
            return item.get("event") or ""
    return ""


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

def load_orthodox_ics(path: Path, url: str, allow_download: bool) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    if not allow_download or not url:
        return ""
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    text = r.content.decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def unfold_ics_lines(text: str) -> List[str]:
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def parse_ics_events(lines: List[str]) -> List[Tuple[date, str]]:
    events: List[Tuple[date, str]] = []
    in_event = False
    cur_date: date | None = None
    cur_summary: str | None = None

    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            cur_date = None
            cur_summary = None
            continue
        if line == "END:VEVENT" and in_event:
            if cur_date and cur_summary:
                events.append((cur_date, cur_summary))
            in_event = False
            continue
        if not in_event:
            continue

        if line.startswith("DTSTART"):
            value = line.split(":", 1)[1].strip()
            date_str = value[:8]
            try:
                cur_date = datetime.strptime(date_str, "%Y%m%d").date()
            except ValueError:
                cur_date = None
        elif line.startswith("SUMMARY"):
            cur_summary = line.split(":", 1)[1].strip()

    return events


def is_major_orthodox(summary: str) -> bool:
    lowered = summary.lower()
    return any(key in lowered for key in ORTHODOX_KEYWORDS)


def get_orthodox_holidays(today: date, ics_text: str) -> List[str]:
    if not ics_text:
        return []
    try:
        lines = unfold_ics_lines(ics_text)
        events = parse_ics_events(lines)
        matches: List[str] = []
        for dt, summary in events:
            if dt == today and is_major_orthodox(summary):
                matches.append(shorten_text(summary, 80))
        # de-duplicate
        seen = set()
        deduped = []
        for item in matches:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped[:2]
    except Exception:
        return []


def get_holidays(today: datetime, ics_text: str) -> str:
    """Return a holiday string or 'Сегодня обычный день'."""
    key = today.strftime("%m-%d")
    items: List[str] = []
    fixed = HOLIDAYS_FIXED.get(key)
    if fixed:
        items.append(fixed)

    orthodox = get_orthodox_holidays(today.date(), ics_text)
    if orthodox:
        items.append(f"Православный: {orthodox[0]}")

    if not items:
        return "Сегодня спокойный день"
    return " / ".join(items[:2])


# -----------------------------
# News (RSS)
# -----------------------------

def is_negative_news(title: str) -> bool:
    lowered = title.lower()
    return any(key in lowered for key in NEGATIVE_KEYWORDS)


def get_news(
    rss_urls: List[str],
    limit: int = DEFAULT_NEWS_LIMIT,
    title_max: int = DEFAULT_NEWS_TITLE_MAX,
) -> List[str]:
    items: List[str] = []
    scan_limit = max(limit * 3, limit)
    for url in rss_urls:
        if not url:
            continue
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:scan_limit]:
                title = (entry.get("title") or "").strip()
                if not title:
                    continue
                title = normalize_space(title)
                if is_negative_news(title):
                    continue
                items.append(shorten_text(title, title_max))
        except Exception:
            continue

    # de-duplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for t in items:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped[:limit]


# -----------------------------
# LLM (Groq)
# -----------------------------

def build_prompt(
    weather: Dict[str, str],
    holidays: str,
    traditions: str,
    history_event: str,
    news: List[str],
    max_chars: int,
    max_lines: int,
    news_limit: int,
    news_title_max: int,
) -> str:
    weather_lines = "\n".join([f"• {city}: {desc}" for city, desc in weather.items()])
    news_lines = "\n".join([f"• {n}" for n in news]) if news else "• Сегодня без заметных местных новостей"
    traditions_line = traditions if traditions else ""
    history_line = history_event if history_event else ""

    return textwrap.dedent(
        f"""
        Ты — семейный Telegram‑бот. Пиши очень коротко и тепло.
        Ограничения: не больше {max_lines} строк и {max_chars} символов.
        Никакой политики, тревожных тем и негатива.

        Структура:
        1) Приветствие + эмодзи (1 строка)
        2) Погода: 3 коротких пункта (Сургут/Тюмень/Москва)
        3) Праздники: 1 строка (максимум 2 праздника; если нет — «Сегодня спокойный день»)
        4) Традиции: 1 строка, если есть (Масленица/пост/русские традиции)
        5) История: 1 строка, если есть (позитивное историческое событие)
        6) Новости: 1–{news_limit} очень коротких пункта (≤ {news_title_max} символов)
        7) Короткая ободряющая фраза (1 строка)

        Если новостей нет — оставь строку «Сегодня без заметных местных новостей».
        Не добавляй ссылки и хэштеги.

        Данные:
        Погода:
        {weather_lines}

        Праздники:
        {holidays}

        Традиции:
        {traditions_line}

        История:
        {history_line}

        Новости:
        {news_lines}
        """
    ).strip()


def build_fallback_post(
    weather: Dict[str, str],
    holidays: str,
    traditions: str,
    history_event: str,
    news: List[str],
    today: datetime,
) -> str:
    greeting = "Доброе утро, семья! ☀️" if 5 <= today.hour < 12 else "Привет, семья! 🙂"
    weather_line = f"Погода: {format_weather_inline(weather)}"
    holiday_line = f"Праздники: {holidays}"

    lines: List[str] = [greeting, weather_line, holiday_line]
    if traditions:
        lines.append(f"Традиции: {traditions}")
    if history_event:
        lines.append(f"История: {history_event}")

    if news:
        news_line = "Новости: " + "; ".join(news)
        lines.append(news_line)
    else:
        lines.append("Новости: Сегодня без заметных местных новостей")

    lines.append(pick_encouraging_phrase(today.date()))
    return "\n".join(lines)


def extract_message_content(data: dict) -> str:
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return ""
    content = msg.get("content") or ""
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(part.get("text") or "")
            elif isinstance(part, str):
                parts.append(part)
        content = "".join(parts)
    return str(content).strip()


def generate_openrouter_post(prompt: str, api_key: str, model: str) -> str:
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
        "temperature": 0.5,
        "max_tokens": 220,
    }

    r = requests.post(OPENROUTER_API_URL, headers=headers, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return extract_message_content(r.json())


def generate_zai_post(
    prompt: str,
    api_key: str,
    model: str,
    base_url: str,
    thinking_mode: str,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 220,
    }
    if thinking_mode.lower() in {"disabled", "off", "no"}:
        payload["thinking"] = {"type": "disabled"}

    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return extract_message_content(r.json())


def generate_post(
    prompt: str,
    openrouter_key: str | None,
    openrouter_model: str,
    zai_key: str | None,
    zai_model: str,
    zai_base: str,
    zai_thinking: str,
) -> str:
    if zai_key:
        try:
            return generate_zai_post(prompt, zai_key, zai_model, zai_base, zai_thinking)
        except Exception:
            return ""
    if openrouter_key:
        try:
            return generate_openrouter_post(prompt, openrouter_key, openrouter_model)
        except Exception:
            return ""
    return ""


def enforce_post_limits(text: str, max_chars: int, max_lines: int) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    compact = "\n".join(lines)
    if len(compact) <= max_chars:
        return compact
    trimmed = compact[:max_chars]
    if "\n" in trimmed:
        trimmed = trimmed.rsplit("\n", 1)[0].rstrip()
    return trimmed


# -----------------------------
# Telegram
# -----------------------------

def split_text(text: str, max_len: int) -> List[str]:
    parts: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            parts.append(remaining)
            break
        cut = remaining.rfind("\n", 0, max_len)
        if cut == -1 or cut < max_len * 0.5:
            cut = max_len
        parts.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return parts


def send_telegram(token: str, chat_id: str, text: str, max_len: int) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    safe_text = html.escape(text)
    for chunk in split_text(safe_text, max_len=max_len):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
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
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    zai_key = os.getenv("ZAI_API_KEY")
    if not zai_key and not openrouter_key:
        print("Missing required env var: ZAI_API_KEY or OPENROUTER_API_KEY", file=sys.stderr)
        return 1

    openrouter_model = os.getenv("OPENROUTER_MODEL", "z-ai/glm-4.5-air:free")
    zai_model = os.getenv("ZAI_MODEL", "glm-4.7")
    zai_base = os.getenv("ZAI_API_BASE", ZAI_API_BASE_DEFAULT)
    zai_thinking = os.getenv("ZAI_THINKING", "disabled")
    orthodox_url = os.getenv("ORTHODOX_ICAL_URL", DEFAULT_ORTHODOX_ICAL_URL)
    orthodox_path = Path(os.getenv("ORTHODOX_ICAL_PATH", DEFAULT_ORTHODOX_ICAL_PATH))
    orthodox_allow_download = os.getenv("ORTHODOX_ALLOW_DOWNLOAD", str(DEFAULT_ORTHODOX_ALLOW_DOWNLOAD)) == "1"
    traditions_path = Path(os.getenv("TRADITIONS_PATH", DEFAULT_TRADITIONS_PATH))
    history_path = Path(os.getenv("HISTORICAL_EVENTS_PATH", DEFAULT_HISTORY_PATH))

    max_post_chars = get_int_env("MAX_POST_CHARS", DEFAULT_MAX_POST_CHARS)
    max_post_lines = get_int_env("MAX_POST_LINES", DEFAULT_MAX_POST_LINES)
    news_limit = get_int_env("NEWS_MAX_ITEMS", DEFAULT_NEWS_LIMIT)
    news_title_max = get_int_env("NEWS_TITLE_MAX", DEFAULT_NEWS_TITLE_MAX)

    rss_surgut = os.getenv("RSS_SURGUT", "").strip()
    rss_moscow = os.getenv("RSS_MOSCOW", "").strip()
    rss_urls = [rss_surgut, rss_moscow]

    weather = get_weather()
    orthodox_ics = load_orthodox_ics(orthodox_path, orthodox_url, orthodox_allow_download)
    holidays = get_holidays(datetime.now(), orthodox_ics)
    traditions = get_traditions(datetime.now().date(), traditions_path)
    history_event = get_historical_event(datetime.now().date(), history_path)
    news = get_news(rss_urls, limit=news_limit, title_max=news_title_max)

    prompt = build_prompt(
        weather,
        holidays,
        traditions,
        history_event,
        news,
        max_post_chars,
        max_post_lines,
        news_limit,
        news_title_max,
    )
    post = generate_post(
        prompt,
        openrouter_key,
        openrouter_model,
        zai_key,
        zai_model,
        zai_base,
        zai_thinking,
    )
    post = enforce_post_limits(post, max_post_chars, max_post_lines)

    if not post.strip():
        post = build_fallback_post(weather, holidays, traditions, history_event, news, datetime.now())
        post = enforce_post_limits(post, max_post_chars, max_post_lines)

    send_telegram(tg_token, tg_chat, post, max_len=max_post_chars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
