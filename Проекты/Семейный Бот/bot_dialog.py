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
RELATIONS_PATH = Path("data/family_relations.json")

QUIET_START = 22  # 22:00
QUIET_END = 6     # 06:00

MORNING_HOUR = 6
EVENING_HOUR = 20
PARENT_NOTIFY_HOUR = 21
DEFAULT_LIST_NAME = "покупки"

ZAI_API_BASE_DEFAULT = "https://api.z.ai/api/paas/v4"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

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
        state = {"profiles": {}, "pending": [], "last_update_id": 0}
        ensure_family_settings(state)
        ensure_lists(state)
        ensure_reminders(state)
        return state
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        ensure_family_settings(state)
        ensure_lists(state)
        ensure_reminders(state)
        return state
    except Exception:
        state = {"profiles": {}, "pending": [], "last_update_id": 0}
        ensure_family_settings(state)
        ensure_lists(state)
        ensure_reminders(state)
        return state


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_family_settings(state: Dict[str, Any]) -> Dict[str, Any]:
    fs = state.setdefault("family_settings", {})
    fs.setdefault("parent_ids", [])
    fs.setdefault("notify_hour", PARENT_NOTIFY_HOUR)
    return fs


def ensure_lists(state: Dict[str, Any]) -> Dict[str, List[dict]]:
    return state.setdefault("lists", {})


def ensure_reminders(state: Dict[str, Any]) -> List[dict]:
    return state.setdefault("reminders", [])


def send_message(token: str, chat_id: int, text: str, state: Dict[str, Any], reply_markup: Optional[dict] = None) -> None:
    ts = now_local()
    if in_quiet_hours(ts):
        # queue for morning
        item = {
            "chat_id": chat_id,
            "text": text,
            "send_after": (ts.replace(hour=QUIET_END, minute=0, second=0, microsecond=0) + timedelta(days=1 if ts.hour >= QUIET_START else 0)).isoformat(),
        }
        if reply_markup:
            item["reply_markup"] = reply_markup
        state.setdefault("pending", []).append(item)
        save_state(state)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
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
                send_message(token, int(item["chat_id"]), item["text"], state, reply_markup=item.get("reply_markup"))
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


def load_relations() -> Dict[str, Any]:
    if not RELATIONS_PATH.exists():
        return {}
    try:
        return json.loads(RELATIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", (name or "").lower())


def profile_name(profile: Dict[str, Any]) -> str:
    return (
        profile.get("name")
        or profile.get("address_as")
        or profile.get("tg_first_name")
        or ""
    )


def update_profile_from_user(profile: Dict[str, Any], user: Dict[str, Any]) -> None:
    if not user:
        return
    profile["tg_first_name"] = user.get("first_name") or profile.get("tg_first_name") or ""
    profile["tg_last_name"] = user.get("last_name") or profile.get("tg_last_name") or ""
    profile["tg_username"] = user.get("username") or profile.get("tg_username") or ""


def start_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "Начать ✨"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def role_keyboard() -> dict:
    return {
        "keyboard": [
            [{"text": "Ребёнок"}, {"text": "Взрослый"}],
            [{"text": "Бабушка"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def cancel_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "Отмена"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def delete_confirm_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "Да, удалить"}], [{"text": "Отмена"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def main_menu_keyboard(profile: Dict[str, Any]) -> dict:
    audience = profile.get("audience") or ("child" if is_child_profile(profile) else "adult")
    if audience == "child":
        keyboard = [
            [{"text": "Моё расписание"}, {"text": "Добавить в расписание"}],
            [{"text": "Мои дела"}, {"text": "Добавить дело"}],
            [{"text": "Отметить дело"}, {"text": "Интересный факт"}],
            [{"text": "Идея на выходной"}, {"text": "Напоминание"}],
            [{"text": "Дни рождения"}, {"text": "Указать ДР"}],
            [{"text": "Помощь"}, {"text": "Удалить мои данные"}],
        ]
    elif audience == "grandma":
        keyboard = [
            [{"text": "Напоминание"}, {"text": "Мои напоминания"}],
            [{"text": "Дни рождения"}, {"text": "Указать ДР"}],
            [{"text": "Помощь"}, {"text": "Удалить мои данные"}],
        ]
    else:
        keyboard = [
            [{"text": "Список покупок"}, {"text": "Добавить в список"}],
            [{"text": "Отметить в списке"}, {"text": "Очистить список"}],
            [{"text": "Расписание"}, {"text": "Добавить в расписание"}],
            [{"text": "Мои дела"}, {"text": "Добавить дело"}],
            [{"text": "Отметить дело"}, {"text": "Напоминание"}],
            [{"text": "Мои напоминания"}, {"text": "Дни рождения"}],
            [{"text": "Указать ДР"}, {"text": "Помощь"}],
            [{"text": "Удалить мои данные"}],
        ]
    return {"keyboard": keyboard, "resize_keyboard": True}


def classify_audience(text: str) -> Optional[str]:
    t = (text or "").lower()
    grandma_markers = ["бабуш", "баба ", "баба", "бабуля", "бабушка", "бабуля"]
    adult_markers = ["мама", "пап", "отец", "мать", "дедуш", "дяд", "тет", "муж", "жена", "родител", "админ", "создател", "взросл", "опекун"]
    child_markers = ["реб", "сын", "дочь", "мальчик", "девоч", "школьник", "дошкол"]
    if any(k in t for k in grandma_markers):
        return "grandma"
    if any(k in t for k in adult_markers):
        return "adult"
    if any(k in t for k in child_markers):
        return "child"
    return None


def is_child_profile(profile: Dict[str, Any]) -> bool:
    audience = profile.get("audience")
    if audience == "child":
        return True
    if audience in {"adult", "grandma"}:
        return False
    role = (profile.get("role") or "")
    inferred = classify_audience(role)
    if inferred == "child":
        return True
    if inferred in {"adult", "grandma"}:
        return False
    if profile.get("is_child") is True:
        return True
    if profile.get("is_child") is False:
        return False
    age = profile.get("age")
    return age is not None and age < 18


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


def weekend_fact(profile: Dict[str, Any]) -> str:
    fact = pick_fact(profile)
    if fact:
        return f"Интересный факт: {fact}"
    return "Хочешь, я добавлю ещё фактов?"


def weekend_idea(profile: Dict[str, Any]) -> str:
    interests = [s.lower() for s in (profile.get("interests") or [])]
    ideas_by_interest = {
        "рис": ["Сделай рисунок природы или любимого героя.", "Попробуй нарисовать комикс из 3 кадров."],
        "спорт": ["Поиграй в футбол или попрыгай со скакалкой.", "Сделай мини‑зарядку на 5 минут."],
        "муз": ["Послушай новый жанр музыки и опиши, что понравилось.", "Попробуй подобрать простую мелодию."],
        "чит": ["Прочитай главу книги и перескажи 3 интересных факта.", "Найди короткую статью про то, что тебе нравится."],
        "робот": ["Собери или придумай маленький проект с роботами.", "Посмотри, как устроен простой датчик."],
        "лего": ["Собери что‑то новое из LEGO и покажи фото.", "Попробуй построить мост, который выдержит груз."],
    }
    for key, ideas in ideas_by_interest.items():
        if any(key in it for it in interests):
            return random.choice(ideas)
    generic = [
        "Сходи на прогулку и сфотографируй что‑то необычное.",
        "Сделай мини‑челлендж: 10 приседаний и 10 отжиманий (если можно).",
        "Собери пазл или придумай настольную игру из подручных вещей.",
    ]
    return random.choice(generic)


def _next_reminder_id(reminders: List[dict]) -> int:
    if not reminders:
        return 1
    return max(int(r.get("id", 0)) for r in reminders) + 1


def _build_datetime(year: int, month: int, day: int, hour: int, minute: int) -> Optional[datetime]:
    try:
        return datetime(year, month, day, hour, minute, tzinfo=TZ)
    except Exception:
        return None


def parse_remind_args(args: str, now: datetime) -> tuple[Optional[datetime], Optional[str], Optional[str]]:
    args = args.strip()
    if not args:
        return None, None, "Формат: /remind 18:00 текст"

    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})\s+(.+)", args)
    if m:
        y, mo, d, hh, mm, text = m.groups()
        dt = _build_datetime(int(y), int(mo), int(d), int(hh), int(mm))
        if not dt:
            return None, None, "Неверная дата."
        if dt <= now:
            return None, None, "Эта дата уже прошла."
        return dt, text.strip(), None

    m = re.match(r"(\d{1,2})[./](\d{1,2})\s+(\d{1,2}):(\d{2})\s+(.+)", args)
    if m:
        d, mo, hh, mm, text = m.groups()
        year = now.year
        dt = _build_datetime(year, int(mo), int(d), int(hh), int(mm))
        if not dt:
            return None, None, "Неверная дата."
        if dt <= now:
            dt = _build_datetime(year + 1, int(mo), int(d), int(hh), int(mm))
        return dt, text.strip(), None

    m = re.match(r"(\d{1,2}):(\d{2})\s+(.+)", args)
    if m:
        hh, mm, text = m.groups()
        dt = _build_datetime(now.year, now.month, now.day, int(hh), int(mm))
        if not dt:
            return None, None, "Неверное время."
        if dt <= now:
            dt = dt + timedelta(days=1)
        return dt, text.strip(), None

    return None, None, "Формат: /remind 18:00 текст или /remind 25.02 18:00 текст"


def add_reminder(state: Dict[str, Any], chat_id: int, when: datetime, text: str) -> int:
    reminders = ensure_reminders(state)
    rid = _next_reminder_id(reminders)
    reminders.append({
        "id": rid,
        "chat_id": int(chat_id),
        "text": text,
        "due_at": when.isoformat(),
        "created_at": now_local().isoformat(),
    })
    return rid


def list_reminders(state: Dict[str, Any], chat_id: int) -> str:
    reminders = [r for r in ensure_reminders(state) if int(r.get("chat_id", 0)) == int(chat_id)]
    if not reminders:
        return "Напоминаний пока нет."
    def _sort_key(r: dict):
        try:
            return datetime.fromisoformat(r.get("due_at", ""))
        except Exception:
            return now_local()
    reminders.sort(key=_sort_key)
    lines = []
    for r in reminders[:20]:
        try:
            dt = datetime.fromisoformat(r.get("due_at", ""))
            when = dt.strftime("%d.%m %H:%M")
        except Exception:
            when = "?"
        lines.append(f"{r.get('id')}. {when} — {r.get('text')}")
    return "Напоминания:\n" + "\n".join(lines)


def delete_reminder(state: Dict[str, Any], chat_id: int, rid: int) -> bool:
    reminders = ensure_reminders(state)
    kept = []
    removed = False
    for r in reminders:
        if int(r.get("chat_id", 0)) == int(chat_id) and int(r.get("id", -1)) == int(rid):
            removed = True
            continue
        kept.append(r)
    state["reminders"] = kept
    return removed


def process_reminders(token: str, state: Dict[str, Any]) -> None:
    ts = now_local()
    reminders = ensure_reminders(state)
    if not reminders:
        return
    remaining = []
    for r in reminders:
        try:
            due = datetime.fromisoformat(r.get("due_at", ""))
        except Exception:
            continue
        if due <= ts:
            try:
                send_message(token, int(r.get("chat_id")), f"⏰ Напоминание: {r.get('text')}", state)
            except Exception:
                remaining.append(r)
        else:
            remaining.append(r)
    state["reminders"] = remaining


def parse_daymonth(value: str) -> Optional[tuple[int, int]]:
    m = re.match(r"(\d{1,2})[./](\d{1,2})", value.strip())
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    return day, month


def list_birthdays(state: Dict[str, Any]) -> str:
    rel = load_relations()
    entries: Dict[str, str] = {}
    for child in rel.get("children", []):
        name = child.get("name")
        bday = child.get("birthday")
        if name and bday:
            entries[name] = bday
    for prof in state.get("profiles", {}).values():
        name = profile_name(prof)
        bday = prof.get("birthday")
        if name and bday:
            entries[name] = bday
    items = []
    for name, bday in entries.items():
        dm = parse_daymonth(bday)
        if not dm:
            continue
        day, month = dm
        items.append((month, day, name, bday))
    if not items:
        return "Пока нет дат дней рождения."
    items.sort()
    lines = [f"{bday} — {name}" for _, _, name, bday in items]
    return "Дни рождения:\n" + "\n".join(lines)


def ensure_list_name(name: str) -> str:
    return name.strip() or DEFAULT_LIST_NAME


def parse_list_add(args: str) -> tuple[str, Optional[str]]:
    if not args:
        return DEFAULT_LIST_NAME, None
    if "|" in args:
        list_name, item = args.split("|", 1)
        return ensure_list_name(list_name), item.strip() or None
    return DEFAULT_LIST_NAME, args.strip()


def parse_list_done(args: str) -> tuple[str, Optional[int]]:
    parts = args.split()
    if not parts:
        return DEFAULT_LIST_NAME, None
    if parts[-1].isdigit():
        idx = int(parts[-1])
        name = " ".join(parts[:-1])
        return ensure_list_name(name), idx
    return DEFAULT_LIST_NAME, None


def add_shared_item(state: Dict[str, Any], name: str, text: str, user_id: int) -> None:
    lists = ensure_lists(state)
    items = lists.setdefault(name, [])
    items.append({"text": text, "done": False, "created": now_local().isoformat(), "by": int(user_id)})


def complete_shared_item(state: Dict[str, Any], name: str, idx: int) -> bool:
    items = ensure_lists(state).get(name, [])
    if idx < 1 or idx > len(items):
        return False
    items[idx - 1]["done"] = True
    return True


def clear_shared_list(state: Dict[str, Any], name: str, all_items: bool = False) -> int:
    lists = ensure_lists(state)
    items = lists.get(name, [])
    if not items:
        return 0
    if all_items:
        removed = len(items)
        lists[name] = []
        return removed
    remaining = [i for i in items if not i.get("done")]
    removed = len(items) - len(remaining)
    lists[name] = remaining
    return removed


def list_names(state: Dict[str, Any]) -> str:
    lists = ensure_lists(state)
    if not lists:
        return "Пока нет списков. Добавьте: /list add продукты | молоко"
    names = ", ".join(sorted(lists.keys()))
    return f"Списки: {names}"


def format_shared_list(state: Dict[str, Any], name: str) -> str:
    lists = ensure_lists(state)
    items = lists.get(name, [])
    if not items:
        return f"Список «{name}» пуст."
    lines = []
    for i, t in enumerate(items, 1):
        mark = "✅" if t.get("done") else "⬜️"
        lines.append(f"{mark} {i}. {t.get('text')}")
    return f"Список «{name}»:\n" + "\n".join(lines)


def _relations_parents_for(child_name: str, relations: Dict[str, Any]) -> List[str]:
    if not child_name or not relations:
        return []
    n = normalize_name(child_name)
    for item in relations.get("children", []):
        names = [item.get("name", "")] + item.get("aliases", [])
        if any(normalize_name(x) == n for x in names if x):
            return item.get("parents", []) or []
    return []


def notify_parents(token: str, state: Dict[str, Any], child_id: int, child_profile: Dict[str, Any], message: str) -> None:
    parents = ensure_family_settings(state).get("parent_ids", [])
    if not parents:
        return
    child_name = profile_name(child_profile) or "Ребёнок"
    relations = load_relations()
    target_parent_names = _relations_parents_for(child_name, relations)

    selected_parents = []
    if target_parent_names:
        for pid in parents:
            pprof = state.get("profiles", {}).get(str(pid), {})
            pname = profile_name(pprof)
            if any(normalize_name(pname) == normalize_name(x) for x in target_parent_names):
                selected_parents.append(pid)
    if not selected_parents:
        selected_parents = parents

    for pid in selected_parents:
        try:
            if int(pid) == int(child_id):
                continue
            send_message(token, int(pid), f"🔔 {child_name}: {message}", state)
        except Exception:
            pass


def profile_for(state: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    profiles = state.setdefault("profiles", {})
    return profiles.setdefault(str(user_id), {
        "name": "",
        "role": "",
        "audience": "",
        "address_as": "",
        "is_child": None,
        "age": None,
        "birthday": "",
        "grade": "",
        "interests": [],
        "schedule": [],
        "todos": [],
        "awaiting": "",
        "pending_list_name": "",
        "last_morning_prompt": "",
        "last_evening_prompt": "",
        "last_user_message_at": "",
        "last_fact_idx": None,
        "last_parent_notify": "",
        "tg_first_name": "",
        "tg_last_name": "",
        "tg_username": "",
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

    if step == "start_confirm":
        low = text.lower()
        if "нач" in low or "/start" in low:
            set_awaiting(profile, "role")
            return (
                "Привет! Я семейный помощник 😊\n"
                "Подскажи, кто ты в семье? (ребёнок/взрослый/бабушка)",
                role_keyboard(),
            )
        return "Нажми кнопку «Начать ✨»."

    if step == "role":
        role_text = text
        profile["role"] = role_text
        inferred = classify_audience(role_text)
        if inferred == "child":
            profile["audience"] = "child"
            profile["is_child"] = True
            set_awaiting(profile, "child_name")
            return "Как тебя зовут?"
        if inferred == "adult":
            profile["audience"] = "adult"
            profile["is_child"] = False
            set_awaiting(profile, "name")
            return "Как тебя зовут?"
        if inferred == "grandma":
            profile["audience"] = "grandma"
            profile["is_child"] = False
            set_awaiting(profile, "name")
            return "Как вас зовут?"
        set_awaiting(profile, "role_confirm")
        return "Ты ребёнок, взрослый или бабушка? (ответь: ребёнок/взрослый/бабушка)"

    if step == "role_confirm":
        role_text = text
        profile["role"] = role_text
        inferred = classify_audience(role_text)
        if inferred == "child":
            profile["audience"] = "child"
            profile["is_child"] = True
            set_awaiting(profile, "child_name")
            return "Как тебя зовут?"
        if inferred == "adult":
            profile["audience"] = "adult"
            profile["is_child"] = False
            set_awaiting(profile, "name")
            return "Как тебя зовут?"
        if inferred == "grandma":
            profile["audience"] = "grandma"
            profile["is_child"] = False
            set_awaiting(profile, "name")
            return "Как вас зовут?"
        return "Пожалуйста, ответь: ребёнок / взрослый / бабушка."

    if step == "child_name":
        profile["name"] = text
        set_awaiting(profile, "age")
        return "Сколько тебе лет?"

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
        return (
            "Спасибо! Я сохранил расписание.\n"
            "Если нужно — просто напиши, и я обновлю.",
            main_menu_keyboard(profile),
        )

    if step == "name":
        profile["name"] = text
        if profile.get("audience") == "grandma":
            set_awaiting(profile, "address_as")
            return "Как к вам обращаться? (например, Баба Маша)"
        set_awaiting(profile, "relation")
        return "Кто ты в семье? (мама/папа/дедушка/дядя/тётя)"

    if step == "relation":
        profile["role"] = text
        if profile.get("audience") == "grandma":
            set_awaiting(profile, "address_as")
            return "Как к вам обращаться? (например, Баба Маша)"
        set_awaiting(profile, "adult_age")
        return "Сколько вам лет? (если не хотите отвечать — напишите «пропустить»)"

    if step == "address_as":
        profile["address_as"] = text
        set_awaiting(profile, "adult_age")
        return "Сколько вам лет? (если не хотите отвечать — напишите «пропустить»)"

    if step == "adult_age":
        if "проп" not in text.lower():
            m = re.search(r"\d+", text)
            if m:
                profile["age"] = int(m.group(0))
        set_awaiting(profile, "")
        return (
            "Спасибо! Готово.\n"
            "Если хотите получать уведомления о детях — напишите «Хочу уведомления».",
            main_menu_keyboard(profile),
        )

    return None


def build_help() -> str:
    return (
        "Пользуйтесь кнопками меню ниже.\n"
        "Что умею: списки, напоминания, расписание и дела, дни рождения, факты и идеи.\n"
        "Если кнопки пропали — напишите «Меню»."
    )


def with_menu(text: str, profile: Dict[str, Any]) -> tuple[str, dict]:
    return text, main_menu_keyboard(profile)


def extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    chunk = text[start:end + 1]
    try:
        return json.loads(chunk)
    except Exception:
        return None


def _fallback_reply() -> str:
    return "Я здесь 🙂 Напиши, что нужно, или нажми «Меню»."


def generate_openrouter_reply(user_text: str, audience: str) -> Optional[str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")
    system = (
        "Ты семейный помощник в личных сообщениях. "
        "Отвечай коротко, дружелюбно и безопасно. "
        "Запрещено: политика, медицина, юридические/финансовые советы, насилие, 18+, радикализация. "
        "Если тема запрещена — вежливо откажись и предложи сменить тему."
    )
    if audience == "child":
        system += " Ответы для ребёнка: простыми словами, без сложных терминов."
    elif audience == "grandma":
        system += " Ответы для бабушки: очень тепло, уважительно, простыми словами, без техничных терминов."
    else:
        system += " Ответы для взрослых: коротко и по делу, без лишней болтовни."

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
        r = requests.post(
            OPENROUTER_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]["content"]
        msg = str(msg).strip() if msg is not None else ""
        return msg or None
    except Exception:
        return None


def generate_openrouter_intent(user_text: str, audience: str) -> Optional[dict]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")
    system = (
        "Ты парсер действий семейного бота. Верни СТРОГО JSON без текста. "
        "Поля: intent (строка), list_name, item, items (массив), index (число), "
        "when (в формате HH:MM или DD.MM HH:MM или YYYY-MM-DD HH:MM), text, date (ДД.ММ), reply. "
        "Допустимые intent: menu, list_add, list_show, list_done, list_clear, todo_add, todo_list, todo_done, "
        "schedule_add, schedule_show, reminder_add, reminder_list, reminder_delete, birthday_set, birthdays, "
        "fact, idea, enable_notifications, disable_notifications, delete_profile, none. "
        "Если пользователь просит интернет‑поиск/ссылки — intent=none и reply: 'Поиск в интернете сейчас отключён. '. "
        "Если не уверен — intent=none и reply с уточнением."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "max_tokens": 180,
    }
    try:
        r = requests.post(
            OPENROUTER_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]["content"]
        msg = str(msg).strip() if msg is not None else ""
        return extract_json(msg)
    except Exception:
        return None


def generate_zai_reply(user_text: str, audience: str) -> str:
    api_key = os.getenv("ZAI_API_KEY")
    if not api_key:
        reply = generate_openrouter_reply(user_text, audience)
        return reply or _fallback_reply()
    model = os.getenv("ZAI_MODEL", "glm-4.7")
    base_url = os.getenv("ZAI_API_BASE", ZAI_API_BASE_DEFAULT)

    def alt_base(url: str) -> str:
        if "/coding/" in url:
            return url.replace("/coding", "")
        if "/api/" in url:
            return url.replace("/api/", "/api/coding/")
        return url

    base_candidates: list[str] = []
    for b in [base_url, alt_base(base_url), ZAI_API_BASE_DEFAULT]:
        if b and b not in base_candidates:
            base_candidates.append(b)

    system = (
        "Ты семейный помощник в личных сообщениях. "
        "Отвечай коротко, дружелюбно и безопасно. "
        "Запрещено: политика, медицина, юридические/финансовые советы, насилие, 18+, радикализация. "
        "Если тема запрещена — вежливо откажись и предложи сменить тему."
    )
    if audience == "child":
        system += " Ответы для ребёнка: простыми словами, без сложных терминов."
    elif audience == "grandma":
        system += " Ответы для бабушки: очень тепло, уважительно, простыми словами, без техничных терминов."
    else:
        system += " Ответы для взрослых: коротко и по делу, без лишней болтовни."

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.5,
        "max_tokens": 160,
    }
    thinking_mode = os.getenv("ZAI_THINKING", "")
    if thinking_mode.lower() in {"disabled", "off", "no"}:
        payload["thinking"] = {"type": "disabled"}

    for base in base_candidates:
        url = base.rstrip("/") + "/chat/completions"
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, data=json.dumps(payload), timeout=20)
            if r.status_code == 429:
                continue
            r.raise_for_status()
            data = r.json()
            msg = data["choices"][0]["message"]["content"]
            if isinstance(msg, list):
                msg = "".join([p.get("text", "") for p in msg if isinstance(p, dict)])
            msg = str(msg).strip() if msg is not None else ""
            if msg:
                return msg
        except Exception:
            continue

    reply = generate_openrouter_reply(user_text, audience)
    return reply or _fallback_reply()


def handle_menu_input(step: str, text: str, user_id: int, profile: Dict[str, Any], state: Dict[str, Any]) -> tuple[str, dict] | str:
    low = text.lower().strip()
    if low in {"отмена", "назад", "cancel"}:
        set_awaiting(profile, "")
        return with_menu("Ок, вернулся в меню.", profile)

    if step == "list_add":
        list_name, item = parse_list_add(text)
        pending = profile.get("pending_list_name")
        if pending and list_name == DEFAULT_LIST_NAME:
            list_name = ensure_list_name(pending)
        profile["pending_list_name"] = ""
        if not item:
            return ("Напишите, что добавить (например: молоко или продукты | молоко).", cancel_keyboard())
        add_shared_item(state, list_name, item, user_id)
        set_awaiting(profile, "")
        save_state(state)
        return with_menu(f"Добавил в список «{list_name}».", profile)

    if step == "list_done":
        list_name, idx = parse_list_done(text)
        pending = profile.get("pending_list_name")
        if pending and list_name == DEFAULT_LIST_NAME:
            list_name = ensure_list_name(pending)
        profile["pending_list_name"] = ""
        if not idx:
            return ("Напишите номер пункта (например: 2) или «продукты 2».", cancel_keyboard())
        ok = complete_shared_item(state, list_name, idx)
        set_awaiting(profile, "")
        save_state(state)
        return with_menu("Готово!" if ok else "Не нашёл такой номер.", profile)

    if step == "list_clear":
        name = ensure_list_name(text or DEFAULT_LIST_NAME)
        pending = profile.get("pending_list_name")
        if pending and name == DEFAULT_LIST_NAME:
            name = ensure_list_name(pending)
        profile["pending_list_name"] = ""
        removed = clear_shared_list(state, name, all_items=False)
        set_awaiting(profile, "")
        save_state(state)
        if removed:
            return with_menu(f"Убрал {removed} пункт(ов) из списка «{name}».", profile)
        return with_menu(f"В списке «{name}» нечего убирать.", profile)

    if step == "remind_input":
        dt, message, err = parse_remind_args(text, now_local())
        if err:
            return (err, cancel_keyboard())
        rid = add_reminder(state, user_id, dt, message)
        set_awaiting(profile, "")
        save_state(state)
        return with_menu(f"Ок! Напомню {dt.strftime('%d.%m %H:%M')} (№{rid}).", profile)

    if step == "birthday_set":
        dm = parse_daymonth(text)
        if not dm:
            return ("Напишите дату в формате ДД.ММ (например, 09.03).", cancel_keyboard())
        profile["birthday"] = f"{dm[0]:02d}.{dm[1]:02d}"
        set_awaiting(profile, "")
        save_state(state)
        return with_menu("Сохранил день рождения.", profile)

    if step == "schedule_add":
        if not text.strip():
            return ("Напишите занятие для расписания.", cancel_keyboard())
        add_schedule(profile, text)
        set_awaiting(profile, "")
        save_state(state)
        return with_menu("Добавил в расписание.", profile)

    if step == "todo_add":
        if not text.strip():
            return ("Напишите, какое дело добавить.", cancel_keyboard())
        add_todo(profile, text)
        set_awaiting(profile, "")
        save_state(state)
        return with_menu("Добавил дело.", profile)

    if step == "todo_done":
        m = re.search(r"\d+", text)
        if not m:
            return ("Напишите номер дела (например: 2).", cancel_keyboard())
        idx = int(m.group(0))
        resp = complete_todo(profile, idx)
        set_awaiting(profile, "")
        save_state(state)
        return with_menu(resp, profile)

    if step == "delete_confirm":
        low = text.lower()
        if "удал" in low or "да" in low:
            state["profiles"].pop(str(user_id), None)
            save_state(state)
            return ("Твои данные удалены. Нажми «Начать ✨».", start_keyboard())
        set_awaiting(profile, "")
        return with_menu("Удаление отменено.", profile)

    set_awaiting(profile, "")
    return with_menu("Готово.", profile)


def handle_message(text: str, user_id: int, profile: Dict[str, Any], state: Dict[str, Any]) -> str:
    profile["last_user_message_at"] = now_local().isoformat()
    save_state(state)

    step = profile.get("awaiting") or ""
    onboarding_steps = {
        "start_confirm",
        "role",
        "role_confirm",
        "child_name",
        "age",
        "grade",
        "birthday",
        "interests",
        "schedule",
        "name",
        "relation",
        "address_as",
        "adult_age",
    }
    menu_steps = {
        "list_add",
        "list_done",
        "list_clear",
        "remind_input",
        "birthday_set",
        "schedule_add",
        "todo_add",
        "todo_done",
        "delete_confirm",
    }

    if step in onboarding_steps:
        resp = handle_onboarding(text, profile)
        save_state(state)
        return resp or "Спасибо!"
    if step in menu_steps:
        resp = handle_menu_input(step, text, user_id, profile, state)
        save_state(state)
        return resp

    norm = text.strip()
    low = norm.lower()

    # soft menu triggers
    if low in {"меню", "menu"}:
        return ("Вот меню:", main_menu_keyboard(profile))
    if low in {"начать", "start"}:
        if profile.get("audience") or profile.get("name"):
            return ("Вот меню:", main_menu_keyboard(profile))
        set_awaiting(profile, "role")
        return (
            "Привет! Я семейный помощник 😊\n"
            "Подскажи, кто ты в семье? (ребёнок/взрослый/бабушка)",
            role_keyboard(),
        )

    if norm.startswith("/start"):
        set_awaiting(profile, "start_confirm")
        save_state(state)
        return (
            "Нажми «Начать ✨», и я задам пару вопросов.",
            start_keyboard(),
        )

    if norm.startswith("/help"):
        return with_menu(build_help(), profile)

    # button/menu text handling
    if low in {"помощь"}:
        return with_menu(build_help(), profile)
    if low in {"список покупок", "покупки", "список"}:
        return with_menu(format_shared_list(state, DEFAULT_LIST_NAME), profile)
    if low in {"добавить в список", "добавить список"}:
        profile["pending_list_name"] = DEFAULT_LIST_NAME
        set_awaiting(profile, "list_add")
        return ("Что добавить в список?", cancel_keyboard())
    if low in {"отметить в списке", "сделал в списке"}:
        profile["pending_list_name"] = DEFAULT_LIST_NAME
        set_awaiting(profile, "list_done")
        return ("Напишите номер пункта (например: 2).", cancel_keyboard())
    if low in {"очистить список", "убрать выполненное"}:
        profile["pending_list_name"] = DEFAULT_LIST_NAME
        set_awaiting(profile, "list_clear")
        return ("Какой список очистить? (по умолчанию «покупки»)", cancel_keyboard())
    if low in {"напоминание", "напомни"}:
        set_awaiting(profile, "remind_input")
        return ("Напишите время и текст: 18:00 позвонить", cancel_keyboard())
    if low in {"мои напоминания"}:
        return with_menu(list_reminders(state, user_id), profile)
    if low in {"моё расписание", "расписание"}:
        return with_menu(format_schedule(profile), profile)
    if low in {"добавить в расписание", "добавить расписание"}:
        set_awaiting(profile, "schedule_add")
        return ("Напишите занятие для расписания.", cancel_keyboard())
    if low in {"мои дела", "дела"}:
        return with_menu(list_todos(profile), profile)
    if low in {"добавить дело"}:
        set_awaiting(profile, "todo_add")
        return ("Какое дело добавить?", cancel_keyboard())
    if low in {"сделал дело", "отметить дело"}:
        set_awaiting(profile, "todo_done")
        return ("Какой номер дела отметить?", cancel_keyboard())
    if low in {"интересный факт", "факт", "факт дня"}:
        return with_menu(weekend_fact(profile), profile)
    if low in {"идея на выходной", "идея"}:
        return with_menu(weekend_idea(profile), profile)
    if low in {"дни рождения"}:
        return with_menu(list_birthdays(state), profile)
    if low in {"указать др", "мой др", "день рождения"}:
        set_awaiting(profile, "birthday_set")
        return ("Напишите дату в формате ДД.ММ (например, 09.03).", cancel_keyboard())
    if low in {"хочу уведомления", "включить уведомления", "уведомления"}:
        if is_child_profile(profile):
            return with_menu("Эта функция только для взрослых.", profile)
        fs = ensure_family_settings(state)
        parents = fs.get("parent_ids", [])
        if user_id not in parents:
            parents.append(user_id)
            fs["parent_ids"] = parents
            save_state(state)
        return with_menu("Уведомления включены.", profile)
    if low in {"отключить уведомления", "не хочу уведомления"}:
        fs = ensure_family_settings(state)
        parents = fs.get("parent_ids", [])
        if user_id in parents:
            parents.remove(user_id)
            save_state(state)
        return with_menu("Уведомления отключены.", profile)
    if low in {"удалить мои данные", "удалить данные", "сбросить данные", "стереть данные"}:
        set_awaiting(profile, "delete_confirm")
        return ("Точно удалить ваши данные?", delete_confirm_keyboard())

    # LLM intent parsing (max use)
    if not norm.startswith("/") and is_allowed(norm):
        audience = profile.get("audience") or ("child" if is_child_profile(profile) else "adult")
        intent_payload = generate_openrouter_intent(norm, audience)
        if intent_payload:
            intent = str(intent_payload.get("intent", "")).strip().lower()
            if intent in {"none", ""}:
                reply = intent_payload.get("reply")
                if reply:
                    return with_menu(reply, profile)
            if intent == "menu":
                return ("Вот меню:", main_menu_keyboard(profile))
            if intent == "list_show":
                name = ensure_list_name(intent_payload.get("list_name") or DEFAULT_LIST_NAME)
                return with_menu(format_shared_list(state, name), profile)
            if intent == "list_add":
                name = ensure_list_name(intent_payload.get("list_name") or DEFAULT_LIST_NAME)
                items = intent_payload.get("items")
                item = intent_payload.get("item")
                if items is None:
                    items = [item] if item else []
                items = [str(x).strip() for x in items if str(x).strip()]
                if not items:
                    profile["pending_list_name"] = name
                    set_awaiting(profile, "list_add")
                    return (f"Что добавить в список «{name}»?", cancel_keyboard())
                for it in items:
                    add_shared_item(state, name, it, user_id)
                save_state(state)
                return with_menu(f"Добавил в список «{name}»: {', '.join(items)}", profile)
            if intent == "list_done":
                name = ensure_list_name(intent_payload.get("list_name") or DEFAULT_LIST_NAME)
                idx = intent_payload.get("index")
                if not idx:
                    profile["pending_list_name"] = name
                    set_awaiting(profile, "list_done")
                    return ("Напишите номер пункта (например: 2).", cancel_keyboard())
                ok = complete_shared_item(state, name, int(idx))
                save_state(state)
                return with_menu("Готово!" if ok else "Не нашёл такой номер.", profile)
            if intent == "list_clear":
                name = ensure_list_name(intent_payload.get("list_name") or DEFAULT_LIST_NAME)
                removed = clear_shared_list(state, name, all_items=False)
                save_state(state)
                if removed:
                    return with_menu(f"Убрал {removed} пункт(ов) из списка «{name}».", profile)
                return with_menu(f"В списке «{name}» нечего убирать.", profile)
            if intent == "todo_add":
                item = (intent_payload.get("item") or intent_payload.get("text") or "").strip()
                if not item:
                    set_awaiting(profile, "todo_add")
                    return ("Какое дело добавить?", cancel_keyboard())
                add_todo(profile, item)
                save_state(state)
                return with_menu("Добавил дело.", profile)
            if intent == "todo_list":
                return with_menu(list_todos(profile), profile)
            if intent == "todo_done":
                idx = intent_payload.get("index")
                if not idx:
                    set_awaiting(profile, "todo_done")
                    return ("Какой номер дела отметить?", cancel_keyboard())
                resp = complete_todo(profile, int(idx))
                save_state(state)
                return with_menu(resp, profile)
            if intent == "schedule_add":
                item = (intent_payload.get("item") or intent_payload.get("text") or "").strip()
                if not item:
                    set_awaiting(profile, "schedule_add")
                    return ("Напишите занятие для расписания.", cancel_keyboard())
                add_schedule(profile, item)
                save_state(state)
                return with_menu("Добавил в расписание.", profile)
            if intent == "schedule_show":
                return with_menu(format_schedule(profile), profile)
            if intent == "reminder_add":
                when = (intent_payload.get("when") or "").strip()
                message = (intent_payload.get("text") or intent_payload.get("item") or "").strip()
                if not when or not message:
                    set_awaiting(profile, "remind_input")
                    return ("Напишите время и текст: 18:00 позвонить", cancel_keyboard())
                dt, msg, err = parse_remind_args(f"{when} {message}", now_local())
                if err:
                    set_awaiting(profile, "remind_input")
                    return (err, cancel_keyboard())
                rid = add_reminder(state, user_id, dt, msg)
                save_state(state)
                return with_menu(f"Ок! Напомню {dt.strftime('%d.%m %H:%M')} (№{rid}).", profile)
            if intent == "reminder_list":
                return with_menu(list_reminders(state, user_id), profile)
            if intent == "reminder_delete":
                idx = intent_payload.get("index")
                if not idx:
                    return with_menu("Напишите номер напоминания.", profile)
                removed = delete_reminder(state, user_id, int(idx))
                save_state(state)
                return with_menu("Удалил напоминание." if removed else "Не нашёл такой номер.", profile)
            if intent == "birthday_set":
                date_val = intent_payload.get("date") or intent_payload.get("item") or ""
                dm = parse_daymonth(str(date_val))
                if not dm:
                    set_awaiting(profile, "birthday_set")
                    return ("Напишите дату в формате ДД.ММ (например, 09.03).", cancel_keyboard())
                profile["birthday"] = f"{dm[0]:02d}.{dm[1]:02d}"
                save_state(state)
                return with_menu("Сохранил день рождения.", profile)
            if intent == "birthdays":
                return with_menu(list_birthdays(state), profile)
            if intent == "fact":
                return with_menu(weekend_fact(profile), profile)
            if intent == "idea":
                return with_menu(weekend_idea(profile), profile)
            if intent == "enable_notifications":
                if is_child_profile(profile):
                    return with_menu("Эта функция только для взрослых.", profile)
                fs = ensure_family_settings(state)
                parents = fs.get("parent_ids", [])
                if user_id not in parents:
                    parents.append(user_id)
                    fs["parent_ids"] = parents
                    save_state(state)
                return with_menu("Уведомления включены.", profile)
            if intent == "disable_notifications":
                fs = ensure_family_settings(state)
                parents = fs.get("parent_ids", [])
                if user_id in parents:
                    parents.remove(user_id)
                    save_state(state)
                return with_menu("Уведомления отключены.", profile)
            if intent == "delete_profile":
                if any(k in low for k in ["удал", "стер", "сброс"]):
                    set_awaiting(profile, "delete_confirm")
                    return ("Точно удалить ваши данные?", delete_confirm_keyboard())

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

    if norm.startswith("/list"):
        args = norm.replace("/list", "", 1).strip()
        if not args:
            return format_shared_list(state, DEFAULT_LIST_NAME)
        if args.startswith("all") or args.startswith("lists"):
            return list_names(state)
        if args.startswith("add"):
            item_args = args.replace("add", "", 1).strip()
            list_name, item = parse_list_add(item_args)
            if not item:
                return "Формат: /list add молоко или /list add продукты | молоко"
            add_shared_item(state, list_name, item, user_id)
            save_state(state)
            return f"Добавил в список «{list_name}»."
        if args.startswith("done"):
            done_args = args.replace("done", "", 1).strip()
            list_name, idx = parse_list_done(done_args)
            if not idx:
                return "Формат: /list done 2 или /list done продукты 2"
            ok = complete_shared_item(state, list_name, idx)
            save_state(state)
            return "Готово!" if ok else "Не нашёл такой номер."
        if args.startswith("clear"):
            clear_args = args.replace("clear", "", 1).strip()
            all_items = False
            list_name = DEFAULT_LIST_NAME
            if clear_args:
                if clear_args.startswith("all"):
                    all_items = True
                    rest = clear_args.replace("all", "", 1).strip()
                    if rest:
                        list_name = ensure_list_name(rest)
                else:
                    list_name = ensure_list_name(clear_args)
            removed = clear_shared_list(state, list_name, all_items=all_items)
            save_state(state)
            if removed:
                return f"Убрал {removed} пункт(ов) из списка «{list_name}»."
            return f"В списке «{list_name}» нечего убирать."
        # treat as list name
        return format_shared_list(state, args)

    if norm.startswith("/remind"):
        args = norm.replace("/remind", "", 1).strip()
        if not args:
            return "Формат: /remind 18:00 текст"
        if args.startswith("list"):
            return list_reminders(state, user_id)
        if args.startswith("delete") or args.startswith("del") or args.startswith("cancel"):
            m = re.search(r"\d+", args)
            if not m:
                return "Формат: /remind delete 2"
            rid = int(m.group(0))
            removed = delete_reminder(state, user_id, rid)
            save_state(state)
            return "Удалил напоминание." if removed else "Не нашёл такой номер."
        dt, text, err = parse_remind_args(args, now_local())
        if err:
            return err
        rid = add_reminder(state, user_id, dt, text)
        save_state(state)
        return f"Ок! Напомню {dt.strftime('%d.%m %H:%M')} (№{rid})."

    if norm.startswith("/birthdays"):
        return list_birthdays(state)

    if norm.startswith("/birthday"):
        args = norm.replace("/birthday", "", 1).strip()
        if args.startswith("set"):
            args = args.replace("set", "", 1).strip()
        dm = parse_daymonth(args) if args else None
        if not dm:
            return "Формат: /birthday set 09.03"
        profile["birthday"] = f"{dm[0]:02d}.{dm[1]:02d}"
        save_state(state)
        return "Сохранил день рождения."

    if norm.startswith("/delete"):
        set_awaiting(profile, "delete_confirm")
        save_state(state)
        return ("Точно удалить ваши данные?", delete_confirm_keyboard())

    if norm.startswith("/parent"):
        if is_child_profile(profile):
            return "Эта команда только для взрослых."
        fs = ensure_family_settings(state)
        parents = fs.get("parent_ids", [])
        if "off" in norm:
            if user_id in parents:
                parents.remove(user_id)
                save_state(state)
            return "Уведомления отключены."
        if user_id not in parents:
            parents.append(user_id)
            fs["parent_ids"] = parents
            save_state(state)
        return "Теперь вы будете получать уведомления о детях."

    if norm.startswith("/fact"):
        save_state(state)
        return weekend_fact(profile)

    if norm.startswith("/idea"):
        save_state(state)
        return weekend_idea(profile)

    low = norm.lower()
    if "факт" in low:
        save_state(state)
        return weekend_fact(profile)
    if any(k in low for k in ["идея", "что делать", "чем заняться", "предложи"]):
        save_state(state)
        return weekend_idea(profile)

    # generic
    if not is_allowed(norm):
        return "Эту тему я не обсуждаю. Давай о чём‑то другом 🙂"

    audience = profile.get("audience") or ("child" if is_child_profile(profile) else "adult")
    return generate_zai_reply(norm, audience)


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
    fs = ensure_family_settings(state)
    notify_hour = fs.get("notify_hour", PARENT_NOTIFY_HOUR)

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

        # parent notify (once per day if no response)
        if ts.hour == notify_hour and not responded_today and profile.get("last_parent_notify") != today_str:
            if fs.get("parent_ids"):
                notify_parents(token, state, int(uid), profile, "не ответил сегодня на сообщения")
                profile["last_parent_notify"] = today_str

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
            process_reminders(token, state)
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
                update_profile_from_user(profile, user)
                response = handle_message(text, user_id, profile, state)
                if response:
                    reply_markup = None
                    text_to_send = response
                    if isinstance(response, tuple):
                        text_to_send, reply_markup = response
                    send_message(token, user_id, text_to_send, state, reply_markup=reply_markup)

            state["last_update_id"] = offset
            save_state(state)
        except Exception:
            time.sleep(3)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
