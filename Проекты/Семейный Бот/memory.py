"""
Family Bot Memory System

Хранит:
- Диалоги пользователей в data/conversations/{user_id}.jsonl
- Саммари диалогов в data/summaries/{user_id}.json
- Краткую память в profile["memory"]
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("familybot_dialog")

# Пути относительно расположения скрипта
BASE_DIR = Path(__file__).parent
CONVERSATIONS_DIR = BASE_DIR / "data" / "conversations"
SUMMARIES_DIR = BASE_DIR / "data" / "summaries"


def init_memory() -> None:
    """Создать директории для памяти"""
    try:
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to init memory dirs: {e}")


def save_message(user_id: int, role: str, text: str, metadata: dict = None) -> None:
    """Сохранить сообщение в историю"""
    try:
        init_memory()
        file = CONVERSATIONS_DIR / f"{user_id}.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "role": role,  # "user" or "assistant"
            "text": text[:2000],  # ограничиваем длину
            "metadata": metadata or {}
        }
        with open(file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to save message: {e}")


def get_recent_messages(user_id: int, limit: int = 50) -> List[dict]:
    """Получить последние N сообщений"""
    try:
        file = CONVERSATIONS_DIR / f"{user_id}.jsonl"
        if not file.exists():
            return []

        messages = []
        with open(file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    messages.append(json.loads(line))

        return messages[-limit:]
    except Exception as e:
        logger.warning(f"Failed to get messages: {e}")
        return []


def save_summary(user_id: int, summary: str, key_facts: List[str]) -> None:
    """Сохранить саммари диалогов"""
    try:
        init_memory()
        file = SUMMARIES_DIR / f"{user_id}.json"
        data = {
            "updated_at": datetime.now().isoformat(),
            "summary": summary,
            "key_facts": key_facts[:20]  # максимум 20 фактов
        }
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save summary: {e}")


def get_summary(user_id: int) -> Optional[dict]:
    """Получить саммари"""
    try:
        file = SUMMARIES_DIR / f"{user_id}.json"
        if not file.exists():
            return None
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to get summary: {e}")
        return None


def build_memory_context(user_id: int, profile: dict) -> str:
    """Построить контекст памяти для LLM"""
    parts = []

    # Базовая информация
    name = profile.get("name", "Пользователь")
    role = profile.get("role", "")
    age = profile.get("age")
    interests = profile.get("interests", [])

    base_info = f"Это {name}"
    if role:
        base_info += f", {role}"
    if age:
        base_info += f", {age} лет"
    parts.append(base_info)

    if interests:
        parts.append(f"Интересы: {', '.join(interests[:5])}")

    # Сохранённая память в профиле
    if profile.get("memory"):
        parts.append(f"О нём/ней: {profile['memory']}")

    # Саммари из файла
    summary = get_summary(user_id)
    if summary:
        parts.append(f"Из прошлых разговоров: {summary['summary']}")
        if summary.get("key_facts"):
            parts.append("Важные факты: " + "; ".join(summary["key_facts"][:5]))

    return "\n".join(parts)


def extract_key_info(text: str) -> List[str]:
    """Извлечь ключевую информацию из текста (простая эвристика)"""
    facts = []
    text_lower = text.lower()

    # Паттерны для извлечения
    patterns = [
        ("мне нравится", "нравится"),
        ("я люблю", "любит"),
        ("я хочу", "хочет"),
        ("я работаю", "работает"),
        ("мой день рождения", "др"),
        ("у меня есть", "имеет"),
        ("я купил", "купил(а)"),
        ("я поехал", "поехал(а)"),
    ]

    for pattern, prefix in patterns:
        if pattern in text_lower:
            # Извлекаем предложение с паттерном
            idx = text_lower.find(pattern)
            end = text.find(".", idx)
            if end == -1:
                end = min(idx + 100, len(text))
            fact = text[idx:end].strip()
            if len(fact) > 10:
                facts.append(f"{prefix}: {fact}")

    return facts[:3]
