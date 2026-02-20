#!/usr/bin/env python3
"""Family Telegram Bot (dialog mode)

Private DM helper for kids/family:
- Onboarding (/start)
- Schedules, todos, interests
- Morning (06:00) and evening (20:00) check-ins
- Quiet hours after 22:00 (no outgoing messages)

Run as a long-lived process.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# -----------------------------
# Config
# -----------------------------
TZ = ZoneInfo("Asia/Yekaterinburg")
STATE_PATH = Path("data/family_state.json")
FACTS_PATH = Path("data/facts.json")

QUIET_START = 22  # 22:00
QUIET_END = 6     # 06:00

MORNING_HOUR = 6
EVENING_HOUR = 20

ZAI_API_BASE_DEFAULT = "https://api.z.ai/api/paas/v4"

NEGATIVE_TOPICS = [
    "политик", "выбор", "войн", "обстрел", "насили", "убий", "криминал",
    "медицин", "болезн", "диагноз", "лекар", "суд", "адвокат", "юрид",
    "финанс", "кредит", "инвест", "бирж", "ставк", "депресс", "суиц",
    "18+", "сексуал", "наркот", "алкогол", "ставки", "казино",
]

# -----------------------------
# Helpers
# -----------------------------

def now_local() -> datetime:
    return datetime.now(tz=TZ)


def in_quiet_hours(ts: datetime) -> bool:
    hour = ts.hour
    return hour >= QUIET_START or hour < QUIET_END


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"profiles": {}, "pending": [], "last_update_id": 0}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"profiles": {}, "pending": [], "last_update_id": 0}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_message(token: str, chat_id: int, text: str, state: Dict[str, Any]) -> None:
    ts = now_local()
    if in_quiet_hours(ts):
        # queue for morning
        state.setdefault("pending", []).append({
            "chat_id": chat_id,
            "text": text,
            "send_after": (ts.replace(hour=QUIET_END, minute=0, second=0, microsecond=0) + timedelta(days=1 if ts.hour >= QUIET_START else 0)).isoformat(),
        })
        save_state(state)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()


def process_pending(token: str, state: Dict[str, Any]) -> None:
    ts = now_local()
    if in_quiet_hours(ts):
        return
    pending = state.get("pending", [])
    if not pending:
        return
    remaining = []
    for item in pending:
        send_after = item.get("send_after")
        try:
            send_after_dt = datetime.fromisoformat(send_after)
        except Exception:
            send_after_dt = ts
        if send_after_dt <= ts:
            try:
                send_message(token, int(item["chat_id"]), item["text"], state)
            except Exception:
                remaining.append(item)
        else:
            remaining.append(item)
    state["pending"] = remaining
    save_state(state)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_allowed(text: str) -> bool:
    lowered = text.lower()
    return not any(bad in lowered for bad in NEGATIVE_TOPICS)


def load_facts() -> List[str]:
    if not FACTS_PATH.exists():
        return []
    try:
        data = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
        return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        return []


def is_child_profile(profile: Dict[str, Any]) -> bool:
    role = (profile.get("role") or "").lower()
    age = profile.get("age")
    return ("реб" in role) or (age is not None and age < 18)


def has_response_today(profile: Dict[str, Any], ts: datetime) -> bool:
    last = profile.get("last_user_message_at")
    if not last:
        return False
    try:
        dt = datetime.fromisoformat(last)
    except Exception:
        return False
    return dt.date() == ts.date()


def pick_fact(profile: Dict[str, Any]) -> Optional[str]:
    facts = load_facts()
    if not facts:
        return None
    last_idx = profile.get("last_fact_idx")
    idx = random.randrange(len(facts))
    if last_idx is not None and len(facts) > 1:
        # try to avoid immediate repeat
        for _ in range(3):
            if idx != last_idx:
                break
            idx = random.randrange(len(facts))
    profile["last_fact_idx"] = idx
    return facts[idx]


def profile_for(state: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    profiles = state.setdefault("profiles", {})
    return profiles.setdefault(str(user_id), {
        "name": "",
        "role": "",
        "age": None,
        "birthday": "",
        "grade": "",
        "interests": [],
        "schedule": [],
        "todos": [],
        "awaiting": "",
        "last_morning_prompt": "",
        "last_evening_prompt": "",
        "last_user_message_at": "",
        "last_fact_idx": None,
    })


def set_awaiting(profile: Dict[str, Any], step: str) -> None:
    profile["awaiting"] = step


def add_schedule(profile: Dict[str, Any], text: str) -> None:
    profile.setdefault("schedule", []).append({"text": text, "created": now_local().isoformat()})


def add_todo(profile: Dict[str, Any], text: str) -> None:
    profile.setdefault("todos", []).append({"text": text, "done": False, "created": now_local().isoformat()})


def list_todos(profile: Dict[str, Any]) -> str:
    items = profile.get("todos", [])
    if not items:
        return "Список дел пуст."
    lines = []
    for i, t in enumerate(items, 1):
        mark = "✅" if t.get("done") else "⬜️"
        lines.append(f"{mark} {i}. {t.get('text')}")
    return "\n".join(lines)


def complete_todo(profile: Dict[str, Any], idx: int) -> str:
    items = profile.get("todos", [])
    if idx < 1 or idx > len(items):
        return "Не нашёл такой номер дела."
    items[idx - 1]["done"] = True
    return "Готово! Отметил как выполненное."


def format_schedule(profile: Dict[str, Any]) -> str:
    items = profile.get("schedule", [])
    if not items:
        return "Расписание пока пустое."
    lines = [f"• {i['text']}" for i in items]
    return "\n".join(lines)


# -----------------------------
# Dialog logic
# -----------------------------

def handle_onboarding(text: str, profile: Dict[str, Any]) -> Optional[str]:
    step = profile.get("awaiting", "")
    text = normalize_text(text)

    if step == "role":
        profile["role"] = text.lower()
        if "реб" in profile["role"] or "д" in profile["role"]:
            set_awaiting(profile, "age")
            return "Сколько тебе лет?"
        set_awaiting(profile, "name")
        return "Как тебя зовут?"

    if step == "age":
        m = re.search(r"\d+", text)
        if m:
            profile["age"] = int(m.group(0))
        set_awaiting(profile, "grade")
        return "В каком ты классе? (если уже учишься)"

    if step == "grade":
        profile["grade"] = text
        set_awaiting(profile, "birthday")
        return "Когда у тебя день рождения? (например, 09.03)"

    if step == "birthday":
        profile["birthday"] = text
        set_awaiting(profile, "interests")
        return "Что тебе интересно? (кружки, хобби)"

    if step == "interests":
        profile["interests"] = [s.strip() for s in text.split(",") if s.strip()]
        set_awaiting(profile, "schedule")
        return "Расскажи своё расписание на будни (когда школа/кружки)."

    if step == "schedule":
        add_schedule(profile, text)
        set_awaiting(profile, "")
        return "Спасибо! Если что-то изменится — просто напиши или используй /schedule add."

    if step == "name":
        profile["name"] = text
        set_awaiting(profile, "relation")
        return "Кто ты в семье? (мама/папа/бабушка/дедушка/дядя/тётя)"

    if step == "relation":
        profile["role"] = text
        set_awaiting(profile, "")
        return "Спасибо! Если захочешь — можешь добавить напоминания или расписание."

    return None


def build_help() -> str:
    return (
        "Команды:\n"
        "/help — помощь\n"
        "/schedule — показать расписание\n"
        "/schedule add <текст> — добавить занятие\n"
        "/todo add <дело> — добавить дело\n"
        "/todo list — список дел\n"
        "/todo done <номер> — отметить выполненным\n"
        "/interest <что интересно> — указать интересы\n"
        "/delete — удалить мои данные"
    )


def generate_zai_reply(user_text: str, is_child: bool) -> str:
    api_key = os.getenv("ZAI_API_KEY")
    if not api_key:
        return "Я понял! Если хочешь, добавь это в расписание (/schedule add ...) или в дела (/todo add ...)."
    model = os.getenv("ZAI_MODEL", "glm-4.7")
    base_url = os.getenv("ZAI_API_BASE", ZAI_API_BASE_DEFAULT)
    url = base_url.rstrip("/") + "/chat/completions"

    system = (
        "Ты семейный помощник в личных сообщениях. "
        "Отвечай коротко, дружелюбно и безопасно. "
        "Запрещено: политика, медицина, юридические/финансовые советы, насилие, 18+, радикализация. "
        "Если тема запрещена — вежливо откажись и предложи сменить тему."
    )
    if is_child:
        system += " Ответы для ребёнка: простыми словами, без сложных терминов."

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.5,
        "max_tokens": 160,
    }
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, data=json.dumps(payload), timeout=20)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]["content"]
        if isinstance(msg, list):
            msg = "".join([p.get("text", "") for p in msg if isinstance(p, dict)])
        return str(msg).strip()
    except Exception:
        return "Я понял! Если хочешь, добавь это в расписание (/schedule add ...) или в дела (/todo add ...)."


def handle_message(text: str, user_id: int, profile: Dict[str, Any], state: Dict[str, Any]) -> str:
    profile["last_user_message_at"] = now_local().isoformat()
    # onboarding
    if profile.get("awaiting"):
        resp = handle_onboarding(text, profile)
        save_state(state)
        return resp or "Спасибо!"

    norm = text.strip()
    if norm.startswith("/start"):
        set_awaiting(profile, "role")
        save_state(state)
        return (
            "Привет! Я семейный помощник 😊\n"
            "Подскажи, кто ты в семье? (ребёнок/мама/папа/бабушка/дедушка)"
        )

    if norm.startswith("/help"):
        return build_help()

    if norm.startswith("/schedule add"):
        item = norm.replace("/schedule add", "").strip()
        if not item:
            return "Напиши текст занятия после команды."
        add_schedule(profile, item)
        save_state(state)
        return "Добавил в расписание."

    if norm.startswith("/schedule"):
        return format_schedule(profile)

    if norm.startswith("/todo add"):
        item = norm.replace("/todo add", "").strip()
        if not item:
            return "Напиши дело после команды."
        add_todo(profile, item)
        save_state(state)
        return "Добавил дело."

    if norm.startswith("/todo list"):
        return list_todos(profile)

    if norm.startswith("/todo done"):
        m = re.search(r"\d+", norm)
        if not m:
            return "Укажи номер дела, например: /todo done 2"
        idx = int(m.group(0))
        resp = complete_todo(profile, idx)
        save_state(state)
        return resp

    if norm.startswith("/interest"):
        item = norm.replace("/interest", "").strip()
        if not item:
            return "Напиши, что тебе интересно."
        profile["interests"] = [s.strip() for s in item.split(",") if s.strip()]
        save_state(state)
        return "Записал интересы."

    if norm.startswith("/delete"):
        state["profiles"].pop(str(user_id), None)
        save_state(state)
        return "Твои данные удалены."

    # generic
    if not is_allowed(norm):
        return "Эту тему я не обсуждаю. Давай о чём‑то другом 🙂"

    is_child = is_child_profile(profile)
    return generate_zai_reply(norm, is_child)


# -----------------------------
# Scheduler
# -----------------------------

def morning_prompt(profile: Dict[str, Any]) -> str:
    return "Доброе утро! Напомни, пожалуйста, своё расписание/планы на сегодня."


def evening_prompt(profile: Dict[str, Any]) -> str:
    return "Как прошёл день? Если что-то меняется в расписании на завтра — напиши."


def weekend_prompt(profile: Dict[str, Any]) -> str:
    fact = pick_fact(profile)
    if fact:
        return f"Выходной! Интересный факт: {fact}\nА как тебе такое? Что удивило больше всего?"
    return "Выходной! Хочешь интересный факт или идею для выходного?"


def run_scheduler(token: str, state: Dict[str, Any]) -> None:
    ts = now_local()
    today_str = ts.date().isoformat()
    is_weekend = ts.weekday() >= 5

    for uid, profile in state.get("profiles", {}).items():
        if not is_child_profile(profile):
            continue
        chat_id = int(uid)
        responded_today = has_response_today(profile, ts)

        # morning
        if ts.hour == MORNING_HOUR and profile.get("last_morning_prompt") != today_str:
            msg = weekend_prompt(profile) if is_weekend else morning_prompt(profile)
            send_message(token, chat_id, msg, state)
            profile["last_morning_prompt"] = today_str

        # evening (re-ask if no response today)
        if ts.hour == EVENING_HOUR and profile.get("last_evening_prompt") != today_str:
            if is_weekend:
                msg = weekend_prompt(profile)
            else:
                if responded_today:
                    msg = evening_prompt(profile)
                else:
                    msg = "Напомню: я жду твоего ответа 🙂 Как прошёл день и какие планы на завтра?"
            send_message(token, chat_id, msg, state)
            profile["last_evening_prompt"] = today_str

    save_state(state)


# -----------------------------
# Main loop
# -----------------------------

def main() -> int:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Missing TELEGRAM_BOT_TOKEN", flush=True)
        return 1

    state = load_state()
    offset = state.get("last_update_id", 0)

    while True:
        try:
            # scheduler & pending
            run_scheduler(token, state)
            process_pending(token, state)

            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"timeout": 25, "offset": offset}
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            updates = r.json().get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat = msg.get("chat", {})
                if chat.get("type") != "private":
                    continue
                text = msg.get("text") or ""
                user = msg.get("from", {})
                user_id = user.get("id")
                if not user_id:
                    continue

                profile = profile_for(state, user_id)
                response = handle_message(text, user_id, profile, state)
                if response:
                    send_message(token, user_id, response, state)

            state["last_update_id"] = offset
            save_state(state)
        except Exception:
            time.sleep(3)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
