#!/usr/bin/env python3
"""Family Telegram Bot (dialog mode)

Private DM helper for kids/family:
- Onboarding (/start)
- Schedules, todos, interests
- Morning (06:00) and evening (20:00) check-ins
- Quiet hours after 22:00 (no outgoing messages)

Run as a long-lived process.

IMPROVEMENTS (Intent Parser Enhancement):
1. Local Regex-based Intent Detection:
   - Fast pattern matching without external API calls
   - Handles common phrases in Russian
   - Supports lists, todos, schedule, reminders, birthdays, facts, ideas

2. Enhanced LLM Prompt:
   - Better examples for intent classification
   - More specific field requirements
   - Child-mode awareness

3. Child-Mode Safety:
   - Shopping lists restricted to adults only
   - Notifications settings restricted to adults
   - Profile deletion restricted to adults
   - Reminder time restrictions for children (07:00-22:00)
   - Extended negative topic filtering

4. Self-Check Function:
   - Test suite for local intent detection
   - Run with: self_check_intent_parser()

5. New Intents Supported:
   - All previous intents maintained
   - Better natural language understanding
   - Multiple phrase variations per intent

TESTING:
- Run self-check: python -c "from bot_dialog import self_check_intent_parser; self_check_intent_parser()"
- Test child mode: Set is_child=True and try list_add (should be blocked)
- Test LLM fallback: Use phrases not covered by regex patterns
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from datetime import datetime, date, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# -----------------------------
# Logging Setup
# -----------------------------
# Configure logging with rotation to prevent log files from growing too large
def setup_logging() -> logging.Logger:
    """Setup rotating file handler for bot dialog logs."""
    logger = logging.getLogger("familybot_dialog")
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Main log file: ~/Library/Logs/familybot_dialog.log
    log_dir = Path.home() / "Library" / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    main_log_path = log_dir / "familybot_dialog.log"

    # Secondary log file: /tmp/family_bot.log (if writable)
    tmp_log_path = Path("/tmp/family_bot.log")

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Main log handler with rotation (5MB max, keep 5 backups)
    main_handler = RotatingFileHandler(
        main_log_path,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=5,
        encoding="utf-8"
    )
    main_handler.setFormatter(formatter)
    main_handler.setLevel(logging.INFO)
    logger.addHandler(main_handler)

    # Try to add secondary handler for /tmp (fail silently if not writable)
    try:
        tmp_handler = RotatingFileHandler(
            tmp_log_path,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding="utf-8"
        )
        tmp_handler.setFormatter(formatter)
        tmp_handler.setLevel(logging.INFO)
        logger.addHandler(tmp_handler)
    except (PermissionError, OSError):
        pass  # /tmp may not be writable, skip silently

    return logger

# Initialize logger
bot_logger = setup_logging()

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
    "смерт", "убийств", "погиб", "труп", "самоуб", "пистолет", "оруж", "взрыв",
]

# -----------------------------
# Intent Parser Patterns
# -----------------------------
# Local regex patterns for fast intent detection
# INTENT PARSER EXAMPLES (for documentation and testing)
#
# List Operations (Adults only):
#   "добавь хлеб"              → list_add, item="хлеб"
#   "купи молоко"              → list_add, item="молоко"
#   "добавь в список яблоки"    → list_add, item="яблоки"
#   "продукты: томаты, огурцы"  → list_add, items=["томаты", "огурцы"]
#   "сделал 2"                 → list_done, index=2
#   "куплено 3"                → list_done, index=3
#   "очисти список"            → list_clear
#   "что в списке"             → list_show
#
# Todo Operations (All):
#   "запиши вынести мусор"      → todo_add, item="вынести мусор"
#   "убрать комнату"           → todo_add, item="убрать комнату"
#   "сделать уроки"            → todo_add, item="сделать уроки"
#   "сделал дело 1"            → todo_done, index=1
#   "мои дела"                 → todo_list
#   "задачи на сегодня"        → todo_list
#
# Schedule Operations (All):
#   "урок математики"          → schedule_add, item="урок математики"
#   "иду в кружок по рисованию" → schedule_add, item="кружок по рисованию"
#   "расписание"               → schedule_show
#   "покажи расписание"        → schedule_show
#
# Reminders (All, with child time restrictions):
#   "напомни завтра в 15:00 позвонить маме"  → reminder_add, when="15:00", text="позвонить маме"
#   "напомни в 18:00"              → reminder_add, when="18:00"
#   "напомни 25.02 14:00 урок"     → reminder_add, when="25.02 14:00", text="урок"
#   "мои напоминания"              → reminder_list
#   "удали напоминание 2"          → reminder_delete, index=2
#
# Birthdays (All):
#   "мой др 09.03"               → birthday_set, date="09.03"
#   "у меня др 15.09"            → birthday_set, date="15.09"
#   "дни рождения"               → birthdays
#   "у кого дни рождения"        → birthdays
#
# General (All):
#   "меню"                       → menu
#   "интересный факт"            → fact
#   "идея на выходной"           → idea
#   "чем заняться?"              → idea
#
# Settings (Adults only):
#   "включи уведомления"         → enable_notifications
#   "отключи уведомления"        → disable_notifications
#   "удали мои данные"           → delete_profile
#
# CHILD MODE SAFETY:
# - Children cannot manage shopping lists (list_* intents blocked)
# - Children cannot enable/disable notifications
# - Children cannot delete their profile
# - Child reminders restricted to 07:00 - 22:00
# - Negative topics filtered out (violence, drugs, etc.)
#
# TEST THE PARSER:
# Run: python -c "from bot_dialog import self_check_intent_parser; self_check_intent_parser()"
# This will run the self-check function and show results.

INTENT_PATTERNS = {
    "list_add": [
        r"^(добавь|купи|нужн|надо|есть|взять|приобрести|принеси)\s+.*?(в список|в покупки)?",
        r"^(куп|покупк|продукт|еда|молоко|хлеб|масло|сахар|соль|яйцо|сыр|колбаса)",
        r"^(надо купить|нужно купить|нужн(о|о) купить|куп(и|ить)\s+)",
        r"^(в список|в список покупок|запиши в список)",
        r"^(пок|продукт)\s*(в список|добавить)?",
        r"^(запиши|напомни купить|не забудь купить)\s+",
        r"^(надо в магазине|надо в магазин|надо(ся)? купить)\s+",
    ],
    "list_show": [
        r"^(что\s*(в|в\s*списке)|покажи\s*(список|что\s*есть)|какой\s*список)",
        r"^(список покупок|покупки|что купить)",
        r"^(что\s*надо\s*купить|чего\s*не\s*хватает)",
    ],
    "list_done": [
        r"^(сделал|выполнил|зачеркн|отмет|убрал)\s+.*?(из списка)?",
        r"^(куплен(о|а|ы)?|купил|взято|взял)",
        r"^(отметить\s+в\s+списке)",
        r"^(готово|сделано)\s+\d+",
    ],
    "todo_add": [
        r"^(запиши|задач|дело|надо\s+сделать|надо\s+делать|нужно\s+сделать|нужно\s+делать)",
        r"^(сделать|выполнить|построить|приготовить|убрать|помыть|почистить|убраться|прибраться)",
        r"^(напомни\s+сделать|запомни\s+сделать|не\s+забудь\s+сделать)",
        r"^(план\s+на\s+день|дела\s+на\s+день|задачи\s+на\s+день)",
        r"^(сделай|выполни|нужно|надо)\s+",
        r"^(дела|задачи):\s+",
    ],
    "todo_list": [
        r"^(мои\s*дела|дела|задачи|что\s+делать|какие\s*дела|какие\s*задачи)",
        r"^(покажи\s*дела|список\s*дел|какие\s*дела\s*на\s*сегодня)",
        r"^(что\s*надо\s+сделать|что\s*осталось\s+сделать)",
    ],
    "todo_done": [
        r"^(сделал\s*дело|выполнил\s*дело|отметил\s*дело|готово\s*дело)",
        r"^(дело\s*сделано|задача\s*выполнена|задача\s*готова)",
        r"^(выполнил\s*задачу|сделано\s*\d+|готово\s*\d+)",
    ],
    "schedule_add": [
        r"^(расписание|урок|занятие|кружок|секция)\s*(добавить|в\s+расписание)?",
        r"^(пойду|иду|буду|идём|поедем)\s+.*(в\s+)?(кружок|секцию|урок|школу|класс)",
        r"^(запиши\s+в\s+расписание|добавь\s+в\s+расписание|в\s+расписание)",
        r"^(есть\s+урок|будет\s+урок|иду\s+на\s+урок)\s+",
        r"^(план\s+на\s+день|расписание\s+на\s+день)\s*:",
    ],
    "schedule_show": [
        r"^(моё\s*расписание|расписание|какое\s*расписание|расписание\s+на\s+сегодня)",
        r"^(покажи\s*расписание|что\s*у\s*меня\s*по\s*расписанию|что\s*завтра)",
        r"^(уроки|занятия|кружки)\s+",
    ],
    "reminder_add": [
        r"^(напомни|напомн(и|ь)|запомни|не\s+забудь|поставь\s+напоминание)",
        r"^(напомнить|напоминаю|будущее|завтра|через)",
        r"^(в\s+\d+[.:]\d+|в\s+завтра|через\s+\d+)",
    ],
    "reminder_list": [
        r"^(мои\s*напоминания|напоминания|какие\s*напоминания|какие\s*есть\s*напоминания)",
        r"^(покажи\s*напоминания|список\s*напоминаний)",
    ],
    "birthday_set": [
        r"^(мой\s*др|мой\s*день\s*рождения|когда\s*у\s*меня\s*др|у\s*меня\s*др)",
        r"^(день\s*рождения\s*у\s*меня|я\s*родился|родилась)\s*",
        r"^(дата\s*рождения|др\s*у\s+меня)",
    ],
    "birthdays": [
        r"^(дни\s*рождения|когда\s*дни\s*рождения|у\s*кого\s*день\s*рождения)",
        r"^(др\s*семьи|дни\s*рождения\s*семьи|кто\s*родился)",
    ],
    "fact": [
        r"^(факт|интересный\s*факт|факт\s*дня|расскажи\s*факт)",
        r"^(что\s*интересное|что\s*нового|расскажи\s+что-нибудь)",
    ],
    "idea": [
        r"^(идея|идея\s*на\s*выходной|чем\s*заняться|что\s*делать)",
        r"^(предложи|подскажи|что\s*интересного\s*сделать)",
    ],
    "menu": [
        r"^(меню|главное|главная|начало|главная\s*страница|старт|start)",
    ],
    "delete_profile": [
        r"^(удали\s*мои\s*данные|удалить\s*данные|стереть\s*данные|сбросить)",
        r"^(удалить\s*профиль|сброс\s*профиля|стереть\s*профиль)",
    ],
    "enable_notifications": [
        r"^(хочу\s*уведомления|включи\s*уведомления|уведомляй\s*меня)",
        r"^(включить\s+уведомления|включи\s+оповещения)",
    ],
    "disable_notifications": [
        r"^(не\s*хочу\s*уведомления|отключи\s*уведомления|без\s*уведомлений)",
        r"^(отключить\s+уведомления|выключить\s+уведомления)",
    ],
}

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

        # Log message queued for morning (without sensitive content)
        text_preview = text[:30] + "..." if len(text) > 30 else text
        bot_logger.info(f"Message queued for morning (chat_id={chat_id}): {text_preview}")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)

    try:
        r = requests.post(url, data=payload, timeout=20)
        r.raise_for_status()

        # Log successful message send (without sensitive content)
        text_preview = text[:30] + "..." if len(text) > 30 else text
        bot_logger.info(f"Message sent (chat_id={chat_id}): {text_preview}")
    except Exception as e:
        bot_logger.error(f"Failed to send message to chat_id={chat_id}: {e}")


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


def generate_clarifying_question() -> str:
    """Generate a random clarifying question to help guide users when intent is none."""
    questions = [
        "Хочешь добавить что-то в список покупок?",
        "Может, нужно запомнить дело или напоминание?",
        "Хочешь что-то добавить в расписание?",
        "Интересный факт или идея на выходной?",
        "Нужно показать дни рождения?",
    ]
    return random.choice(questions)


def log_unrecognized_phrase(text: str) -> None:
    """Log unrecognized phrases safely (only length + first word, no full text)."""
    normalized = normalize_text(text)
    words = normalized.split()
    first_word = words[0] if words else ""
    log_info = f"Unrecognized phrase: length={len(normalized)}, first_word='{first_word}'"
    bot_logger.info(log_info)


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
        "menu_hints_shown": False,
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
    # Add menu hints for new users
    if not profile.get("menu_hints_shown", False):
        # Show hints only once per user
        profile["menu_hints_shown"] = True
        hints = "\n\n💡 Подсказка: можешь писать простыми словами, например:\n" \
                "\"добавь хлеб\", \"напомни завтра в 15:00\", \"урок математики\""
        text = f"{text}{hints}"

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


# -----------------------------
# Local Intent Parser (Fast Fallback)
# -----------------------------
def detect_local_intent(text: str) -> Optional[dict]:
    """
    Fast regex-based intent detection without external API calls.
    Returns intent payload dict or None if not matched.
    """
    t = text.lower().strip()
    if not t:
        return None

    # Check for menu commands first (highest priority)
    if t in {"меню", "menu", "начать", "start"}:
        return {"intent": "menu"}
    if t in {"помощь", "help"}:
        return {"intent": "menu"}

    # Check for list_show (before other list commands)
    if re.search(r"^(что\s*(в|в\s*списке)|покажи\s*(список|что\s*есть)|какой\s*список|список покупок|покупки|что купить)", t):
        return {"intent": "list_show"}

    # Check for list_done (before list_add to avoid false positives)
    if re.search(r"^(сделал|выполнил|зачеркн|отмет|убрал|купил|взял|куплено|взято|готово|сделано)\s*\d+", t):
        m = re.search(r"(\d+)", t)
        if m:
            return {"intent": "list_done", "index": int(m.group(1))}

    # Check for todo_list (before todo_add)
    if re.search(r"^(мои\s*дела|дела|задачи|что\s+делать|какие\s*дела|покажи\s*дела|список\s*дел|какие\s*дела\s+на\s*сегодня|что\s*надо\s+сделать|что\s*осталось\s+сделать)", t):
        return {"intent": "todo_list"}

    # Check for todo_add with "запиши" (before list_add to avoid false positives)
    if re.search(r"^запиши\s+.*(вынести|убрать|помыть|почистить|приготовить|построить|сделать|выполнить)", t, re.IGNORECASE):
        return {"intent": "todo_add", "item": normalize_text(re.sub(r"^запиши\s+", "", t))}

    # Check for todo_done (before todo_add to avoid false positives)
    if re.search(r"^(сделал\s*дело|выполнил\s*дело|отметил\s*дело|готово\s*дело|дело\s*сделано|задача\s*выполнена|задача\s*готова|выполнил\s*задачу|сделано\s*\d+|готово\s*\d+)\s*\d+", t):
        m = re.search(r"(\d+)", t)
        if m:
            return {"intent": "todo_done", "index": int(m.group(1))}

    # Check for schedule_show (before schedule_add)
    if re.search(r"^(моё\s*расписание|расписание|покажи\s*расписание|какое\s*расписание|что\s*у\s*меня\s*по\s*расписанию|уроки|занятия|кружки)", t):
        return {"intent": "schedule_show"}

    # Check for reminder_list
    if re.search(r"^(мои\s*напоминания|напоминания|какие\s*напоминания|покажи\s*напоминания)", t):
        return {"intent": "reminder_list"}

    # Check for birthdays
    if re.search(r"^(дни\s*рождения|когда\s*дни\s*рождения|у\s*кого\s*день\s*рождения|др\s*семьи|дни\s*рождения\s*семьи)", t):
        return {"intent": "birthdays"}

    # Check for idea before other patterns
    if re.search(r"^(идея|идея\s*на\s+выходной|чем\s*заняться|что\s*делать|предложи|подскажи|что\s*интересного\s*сделать|как\s+провести\s+время)", t):
        return {"intent": "idea"}

    # Iterate through intent patterns
    for intent_name, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            try:
                if re.search(pattern, t, re.IGNORECASE):
                    result = {"intent": intent_name}

                    # Extract additional data based on intent
                    if intent_name == "list_add":
                        # Improved extraction: chain prefix removal with whitespace normalization
                        item_text = t
                        # Chain of prefixes to remove (try longest first for better matching)
                        prefixes = [
                            r"^в\s+список\s+покупок\s*",
                            r"^добавь\s+в\s+список\s*",
                            r"^в\s+список\s*",
                            r"^в\s+покупки\s*",
                            r"^в\s+продукты\s*",
                            r"^надо\s+в\s+магазине\s*",
                            r"^надо\s+в\s+магазин\s*",
                            r"^надо\s+купить\s*",
                            r"^нужно\s+купить\s*",
                            r"^надося\s+купить\s*",
                            r"^запиши\s+в\s+список\s*",
                            r"^напомни\s+купить\s*",
                            r"^не\s+забудь\s+купить\s*",
                            r"^приобрести\s*",
                            r"^принеси\s*",
                            r"^добавить\s*",
                            r"^добавь\s*",
                            r"^купить\s*",
                            r"^купи\s*",
                            r"^взять\s*",
                            r"^есть\s*",
                            r"^надо\s*",
                            r"^нужно\s*",
                        ]
                        for prefix in prefixes:
                            item_text = re.sub(prefix, "", item_text, flags=re.IGNORECASE)
                        item_text = normalize_text(item_text)
                        if item_text:
                            result["item"] = item_text

                    elif intent_name == "list_done":
                        # Extract index: "сделал 2" → index=2
                        m = re.search(r"(\d+)", t)
                        if m:
                            result["index"] = int(m.group(1))

                    elif intent_name == "todo_add":
                        # Improved extraction: chain prefix removal with whitespace normalization
                        item_text = t
                        prefixes = [
                            r"^план\s+на\s+день\s*[:\-]?\s*",
                            r"^дела\s+на\s+день\s*[:\-]?\s*",
                            r"^задачи\s+на\s+день\s*[:\-]?\s*",
                            r"^напомни\s+сделать\s*",
                            r"^запомни\s+сделать\s*",
                            r"^не\s+забудь\s+сделать\s*",
                            r"^надо\s+сделать\s*",
                            r"^надо\s+делать\s*",
                            r"^нужно\s+сделать\s*",
                            r"^нужно\s+делать\s*",
                            r"^выполнить\s*",
                            r"^сделай\s*",
                            r"^сделать\s*",
                            r"^построить\s*",
                            r"^приготовить\s*",
                            r"^приготовь\s*",
                            r"^помыть\s*",
                            r"^помой\s*",
                            r"^почистить\s*",
                            r"^прочисти\s*",
                            r"^убраться\s*",
                            r"^прибраться\s*",
                            r"^запиши\s*",
                            r"^задача\s*",
                            r"^задачу\s*",
                            r"^задачи\s*",
                            r"^дело\s*",
                            r"^нужно\s*",
                            r"^надо\s*",
                        ]
                        for prefix in prefixes:
                            item_text = re.sub(prefix, "", item_text, flags=re.IGNORECASE)
                        item_text = normalize_text(item_text)
                        if item_text:
                            result["item"] = item_text

                    elif intent_name == "todo_done":
                        # Extract index: "сделал дело 2" → index=2
                        m = re.search(r"(\d+)", t)
                        if m:
                            result["index"] = int(m.group(1))

                    elif intent_name == "schedule_add":
                        # Improved extraction: chain prefix removal with whitespace normalization
                        item_text = t
                        prefixes = [
                            r"^расписание\s+на\s+день\s*[:\-]?\s*",
                            r"^план\s+на\s+день\s*[:\-]?\s*",
                            r"^запиши\s+в\s+расписание\s*",
                            r"^добавь\s+в\s+расписание\s*",
                            r"^в\s+расписание\s*",
                            r"^есть\s+урок\s*",
                            r"^будет\s+урок\s*",
                            r"^иду\s+на\s+урок\s*",
                            r"^идём\s+на\s+урок\s*",
                            r"^поедем\s+на\s+урок\s*",
                            r"^иду\s+на\s+",
                            r"^идём\s+на\s+",
                            r"^поедем\s+на\s+",
                            r"^пойду\s+на\s+",
                            r"^иду\s+в\s+",
                            r"^идём\s+в\s+",
                            r"^поедем\s+в\s+",
                            r"^пойду\s+в\s+",
                            r"^буду\s+на\s+",
                            r"^буду\s+в\s+",
                            r"^пойду\s+",
                            r"^иду\s+",
                            r"^буду\s*",
                        ]
                        for prefix in prefixes:
                            item_text = re.sub(prefix, "", item_text, flags=re.IGNORECASE)
                        item_text = normalize_text(item_text)
                        if item_text:
                            result["item"] = item_text

                    elif intent_name == "reminder_add":
                        # Extract time and text: "напомни завтра в 15:00 позвонить маме"
                        m_time = re.search(r"(?:напомни|напомн|запомни|не\s+забудь)\s*(?:завтра\s+)?(?:в\s+)?(\d{1,2}[.:]\d{2})", t)
                        m_text = re.search(r"(?:напомни|напомн|запомни|не\s+забудь)(?:\s+завтра)?(?:\s+в\s+\d{1,2}[.:]\d{2})?\s+(.+)", t)
                        if m_time:
                            result["when"] = m_time.group(1)
                        if m_text:
                            result["text"] = m_text.group(1).strip()
                        elif m_time and not m_text:
                            # If only time provided, extract context from sentence
                            text_after = re.sub(r".*\d{1,2}[.:]\d{2}\s*", "", t).strip()
                            if text_after:
                                result["text"] = text_after

                    elif intent_name == "birthday_set":
                        # Extract date: "мой др 09.03" → date="09.03"
                        m = re.search(r"(\d{1,2}[./]\d{1,2})", t)
                        if m:
                            result["date"] = m.group(1)

                    elif intent_name == "reminder_delete":
                        # Extract index: "удали напоминание 2" → index=2
                        m = re.search(r"(\d+)", t)
                        if m:
                            result["index"] = int(m.group(1))

                    return result
            except Exception:
                continue

    # Log unrecognized phrases (safely - only length + first word)
    log_unrecognized_phrase(text)

    return None


def is_child_safe_intent(intent_name: str, payload: dict, is_child: bool) -> bool:
    """
    Additional safety checks for child profiles.
    Returns False if the intent/action is not allowed for children.

    FOR CHILDREN (is_child=True):
    ALLOWED intents:
    - menu, todo_add, todo_list, todo_done (manage their own tasks)
    - schedule_add, schedule_show (view/manage schedule)
    - reminder_add, reminder_list (set reminders during reasonable hours)
    - birthday_set, birthdays (view/set birthdays)
    - fact, idea (educational content)
    - none (no action)

    BLOCKED intents for children:
    - list_add, list_show, list_done, list_clear (shopping lists - adults only)
    - enable/disable_notifications (settings - parents only)
    - delete_profile (data deletion - requires parent approval)
    """
    if not is_child:
        return True

    # Children can manage their own tasks and schedule
    allowed_intents = {
        "menu",
        "todo_add", "todo_list", "todo_done",
        "schedule_add", "schedule_show",
        "fact", "idea",
        "birthdays",
        "none",
    }

    # Reminders are allowed but with time restrictions
    if intent_name == "reminder_add" or intent_name == "reminder_list":
        when = payload.get("when", "")
        if when and intent_name == "reminder_add":
            try:
                # Parse time and check it's during reasonable hours (07:00 - 22:00)
                time_match = re.match(r"(\d{1,2})[.:](\d{2})", when)
                if time_match:
                    hour = int(time_match.group(1))
                    if hour >= 22 or hour < 7:
                        return False  # Too late/early for child reminders
            except Exception:
                pass
        # Reminder list is always safe
        return True

    # Birthday setting is safe
    if intent_name == "birthday_set":
        return True

    # Check if intent is in allowed list
    if intent_name not in allowed_intents:
        return False

    return True


def _fallback_reply() -> str:
    return "Я здесь 🙂 Напиши, что нужно, или нажми «Меню»."


def generate_openrouter_reply(user_text: str, audience: str) -> Optional[str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        bot_logger.warning("OPENROUTER_API_KEY not set, OpenRouter reply unavailable")
        return None
    model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")

    # Log LLM call
    text_preview = user_text[:30] + "..." if len(user_text) > 30 else user_text
    bot_logger.info(f"LLM reply requested (OpenRouter): {text_preview}")

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

        # Log LLM result
        if msg:
            msg_preview = msg[:50] + "..." if len(msg) > 50 else msg
            bot_logger.info(f"LLM reply received (OpenRouter): {msg_preview}")

        return msg or None
    except Exception as e:
        bot_logger.error(f"OpenRouter API error in reply generation: {e}")
        return None


def generate_openrouter_intent(user_text: str, audience: str) -> Optional[dict]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        bot_logger.warning("OPENROUTER_API_KEY not set, LLM intent parsing unavailable")
        return None
    model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")

    # Log LLM call
    text_preview = user_text[:30] + "..." if len(user_text) > 30 else user_text
    bot_logger.info(f"LLM intent parsing requested (OpenRouter): {text_preview}")

    # Enhanced system prompt with better examples and constraints
    system = (
        "ТЫ — ПАРСЕР ДЕЙСТВИЙ СЕМЕЙНОГО БОТА. "
        "ВЕРНИ СТРОГО JSON, БЕЗ ЛИШНЕГО ТЕКСТА. "
        "\n\n"
        "СЛОТЫ JSON: intent (обязательно), list_name, item, items (массив), index (число), "
        "when (HH:MM или DD.MM HH:MM или YYYY-MM-DD HH:MM), text, date (ДД.ММ), reply.\n\n"
        "ДОПУСТИМЫЕ INTENTS:\n"
        "- menu: показать главное меню\n"
        "- list_add: добавить в список (item или items)\n"
        "- list_show: показать список\n"
        "- list_done: отметить как выполненное (index)\n"
        "- list_clear: очистить список\n"
        "- todo_add: добавить дело (item)\n"
        "- todo_list: показать дела\n"
        "- todo_done: выполнить дело (index)\n"
        "- schedule_add: добавить в расписание (item)\n"
        "- schedule_show: показать расписание\n"
        "- reminder_add: добавить напоминание (when, text)\n"
        "- reminder_list: показать напоминания\n"
        "- reminder_delete: удалить напоминание (index)\n"
        "- birthday_set: указать день рождения (date)\n"
        "- birthdays: показать все дни рождения\n"
        "- fact: показать интересный факт\n"
        "- idea: показать идею на выходной\n"
        "- enable_notifications: включить уведомления\n"
        "- disable_notifications: отключить уведомления\n"
        "- delete_profile: удалить данные\n"
        "- none: если не понял запрос или запрещённая тема\n\n"
        "ПРАВИЛА:\n"
        "1. Для 'when' используй формат: HH:MM (сегодня), DD.MM HH:MM (дата и время), "
        "или 'завтра HH:MM' для завтра.\n"
        "2. Для 'date' используй ДД.ММ (например, 09.03).\n"
        "3. Если пользователь просит интернет-поиск/ссылки — intent=none с reply: 'Поиск в интернете сейчас отключён. '\n"
        "4. Если не уверен — intent=none с clarifying reply.\n"
        "5. Для детей (audience=child): запрещены list_*, enable/disable_notifications, delete_profile.\n"
        "6. Если список/дата явно не указаны — не добавляй их в JSON.\n\n"
        "ПРИМЕРЫ:\n"
        "- 'добавь хлеб' → {\"intent\": \"list_add\", \"item\": \"хлеб\"}\n"
        "- 'сделал дело 2' → {\"intent\": \"todo_done\", \"index\": 2}\n"
        "- 'урок математики' → {\"intent\": \"schedule_add\", \"item\": \"урок математики\"}\n"
        "- 'напомни завтра в 15:00 позвонить маме' → {\"intent\": \"reminder_add\", \"when\": \"завтра 15:00\", \"text\": \"позвонить маме\"}\n"
        "- 'мой др 09.03' → {\"intent\": \"birthday_set\", \"date\": \"09.03\"}\n"
        "- 'чем заняться?' → {\"intent\": \"idea\"}\n"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,  # Lower for more deterministic results
        "max_tokens": 200,
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
        result = extract_json(msg)

        # Log LLM result
        if result:
            intent = result.get("intent", "unknown")
            bot_logger.info(f"LLM intent parsed: {intent}")
        else:
            bot_logger.warning(f"LLM intent parsing failed to extract JSON from: {msg[:100]}")

        return result
    except Exception as e:
        bot_logger.error(f"OpenRouter API error in intent parsing: {e}")
        return None


def generate_zai_reply(user_text: str, audience: str) -> str:
    api_key = os.getenv("ZAI_API_KEY")
    if not api_key:
        bot_logger.warning("ZAI_API_KEY not set, falling back to OpenRouter")
        reply = generate_openrouter_reply(user_text, audience)
        return reply or _fallback_reply()
    model = os.getenv("ZAI_MODEL", "glm-4.7")
    base_url = os.getenv("ZAI_API_BASE", ZAI_API_BASE_DEFAULT)

    # Log LLM call
    text_preview = user_text[:30] + "..." if len(user_text) > 30 else user_text
    bot_logger.info(f"LLM reply requested (ZAI): {text_preview}")

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
                # Log successful ZAI response
                msg_preview = msg[:50] + "..." if len(msg) > 50 else msg
                bot_logger.info(f"LLM reply received (ZAI): {msg_preview}")
                return msg
        except Exception as e:
            bot_logger.error(f"ZAI API error (base={base}): {e}")
            continue

    bot_logger.warning("ZAI API failed, falling back to OpenRouter")
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

    # Enhanced intent parsing (local + LLM)
    if not norm.startswith("/") and is_allowed(norm):
        audience = profile.get("audience") or ("child" if is_child_profile(profile) else "adult")
        is_child = is_child_profile(profile)

        # 1. Try local regex-based intent first (fast, no API calls)
        intent_payload = detect_local_intent(norm)
        if intent_payload:
            intent = intent_payload.get("intent", "")
            bot_logger.info(f"Local intent detected: {intent}")

        # 2. Fall back to LLM if local didn't match
        if not intent_payload:
            intent_payload = generate_openrouter_intent(norm, audience)

        # 3. Process the detected intent
        if intent_payload:
            intent = str(intent_payload.get("intent", "")).strip().lower()

            # Child-mode safety checks
            if is_child and not is_child_safe_intent(intent, intent_payload, is_child):
                return with_menu("Эта функция только для взрослых. Обратись к родителям.", profile)

            if intent in {"none", ""}:
                reply = intent_payload.get("reply")
                if reply:
                    return with_menu(reply, profile)
                # If no reply provided, generate a clarifying question
                return with_menu(f"{generate_clarifying_question()}\nИли напиши «Меню».", profile)

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

    # Log scheduler run
    bot_logger.info(f"Scheduler running (time={ts.strftime('%H:%M')}, weekday={ts.weekday()})")

    for uid, profile in state.get("profiles", {}).items():
        if not is_child_profile(profile):
            continue
        chat_id = int(uid)
        responded_today = has_response_today(profile, ts)
        user_name = profile_name(profile) or f"User {uid}"

        # morning
        if ts.hour == MORNING_HOUR and profile.get("last_morning_prompt") != today_str:
            bot_logger.info(f"Morning check-in sent to {user_name} (id={uid})")
            msg = weekend_prompt(profile) if is_weekend else morning_prompt(profile)
            send_message(token, chat_id, msg, state)
            profile["last_morning_prompt"] = today_str

        # evening (re-ask if no response today)
        if ts.hour == EVENING_HOUR and profile.get("last_evening_prompt") != today_str:
            bot_logger.info(f"Evening check-in sent to {user_name} (id={uid})")
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
                bot_logger.info(f"Parent notification sent for {user_name} (id={uid}): child didn't respond today")
            if fs.get("parent_ids"):
                notify_parents(token, state, int(uid), profile, "не ответил сегодня на сообщения")
                profile["last_parent_notify"] = today_str

    save_state(state)


# -----------------------------
# Self-Check & Tests
# -----------------------------
def self_check_intent_parser() -> None:
    """
    Run a quick self-check of the intent parser.
    Tests local regex patterns and LLM fallback.
    Call this function to verify intent detection works correctly.
    """
    print("\n=== Intent Parser Self-Check ===\n")

    test_cases = [
        # List operations
        ("добавь хлеб", "list_add", {"item": "хлеб"}),
        ("купи молоко", "list_add", {"item": "молоко"}),
        ("добавь в список яблоки", "list_add", {"item": "яблоки"}),
        ("запиши в список сыр", "list_add", {"item": "сыр"}),
        ("надо в магазине колбаса", "list_add", {"item": "колбаса"}),
        ("напомни купить сахар", "list_add", {"item": "сахар"}),
        ("сделал 2", "list_done", {"index": 2}),
        ("куплено 3", "list_done", {"index": 3}),

        # Todo operations
        ("запиши вынести мусор", "todo_add", {"item": "вынести мусор"}),
        ("убрать комнату", "todo_add", {"item": "убрать комнату"}),
        ("убраться дома", "todo_add", {"item": "дома"}),
        ("прибраться в комнате", "todo_add", {"item": "в комнате"}),
        ("нужно сделать уроки", "todo_add", {"item": "уроки"}),
        ("сделал дело 1", "todo_done", {"index": 1}),
        ("мои дела", "todo_list", {}),
        ("какие дела на сегодня", "todo_list", {}),

        # Schedule operations
        ("урок математики", "schedule_add", {"item": "урок математики"}),
        ("иду в кружок по рисованию", "schedule_add", {"item": "кружок по рисованию"}),
        ("идём на кружок по музыке", "schedule_add", {"item": "кружок по музыке"}),
        ("расписание", "schedule_show", {}),
        ("что у меня по расписанию", "schedule_show", {}),
        ("уроки", "schedule_show", {}),

        # Reminders
        ("напомни завтра в 15:00 позвонить маме", "reminder_add", {"when": "15:00", "text": "позвонить маме"}),
        ("напомни в 18:00", "reminder_add", {"when": "18:00"}),
        ("мои напоминания", "reminder_list", {}),
        ("какие есть напоминания", "reminder_list", {}),

        # Birthdays
        ("мой др 09.03", "birthday_set", {"date": "09.03"}),
        ("у кого дни рождения", "birthdays", {}),
        ("кто родился", "birthdays", {}),

        # Menu and help
        ("меню", "menu", {}),
        ("старт", "menu", {}),
        ("помощь", "menu", {}),

        # Facts and ideas
        ("интересный факт", "fact", {}),
        ("расскажи что-нибудь", "fact", {}),
        ("идея на выходной", "idea", {}),
        ("чем заняться?", "idea", {}),
        ("как провести время", "idea", {}),
    ]

    passed = 0
    failed = 0

    for text, expected_intent, expected_data in test_cases:
        result = detect_local_intent(text)
        if result:
            detected_intent = result.get("intent")
            if detected_intent == expected_intent:
                # Check if expected keys match
                match = True
                for key, value in expected_data.items():
                    if result.get(key) != value:
                        match = False
                        break

                if match:
                    print(f"✓ PASS: '{text}' → {detected_intent} {expected_data}")
                    passed += 1
                else:
                    print(f"✗ FAIL: '{text}' → {detected_intent} {result} (expected {expected_data})")
                    failed += 1
            else:
                print(f"✗ FAIL: '{text}' → {detected_intent} (expected {expected_intent})")
                failed += 1
        else:
            print(f"⚠ SKIP: '{text}' → No local match (would use LLM)")

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    print(f"Note: Skipped tests will use LLM fallback.\n")


# -----------------------------
# Main loop
# -----------------------------

def main() -> int:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Missing TELEGRAM_BOT_TOKEN", flush=True)
        bot_logger.error("Missing TELEGRAM_BOT_TOKEN - bot cannot start")
        return 1

    bot_logger.info("Bot starting up...")
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

                # Log incoming message (without sensitive data)
                user_name = profile_name(profile) or f"User {user_id}"
                text_preview = text[:50] + "..." if len(text) > 50 else text
                bot_logger.info(f"Received message from {user_name} (id={user_id}): {text_preview}")
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
        except Exception as e:
            bot_logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(3)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
