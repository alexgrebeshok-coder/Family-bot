#!/usr/bin/env python3
"""OpenClaw Token Analyzer - CLI для анализа использования токенов в сессиях."""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

app = typer.Typer(help="Анализатор использования токенов OpenClaw")
console = Console()

# Пути по умолчанию
OPENCLAW_DIR = Path.home() / ".openclaw"
SESSIONS_PATTERN = "agents/*/sessions/*.jsonl"


def find_session_files() -> list[Path]:
    """Найти все JSONL файлы сессий."""
    files = []
    for agent_dir in (OPENCLAW_DIR / "agents").glob("*"):
        sessions_dir = agent_dir / "sessions"
        if sessions_dir.exists():
            files.extend(sessions_dir.glob("*.jsonl"))
    return files


def parse_session_file(file_path: Path) -> dict:
    """Парсинг JSONL файла сессии OpenClaw."""
    result = {
        "file": str(file_path),
        "agent": file_path.parent.parent.name,
        "session_id": file_path.stem,
        "tokens": 0,
        "cost": 0.0,
        "model": None,
        "provider": None,
        "messages": 0,
        "timestamp": None
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    
                    # Вариант 1: usage на верхнем уровне (старый формат)
                    if "usage" in data:
                        usage = data["usage"]
                        result["tokens"] += usage.get("totalTokens", 0)
                        if "cost" in usage:
                            result["cost"] += usage["cost"].get("total", 0)
                    
                    # Вариант 2: usage внутри message (формат OpenClaw)
                    if "message" in data:
                        msg = data["message"]
                        if "usage" in msg:
                            usage = msg["usage"]
                            result["tokens"] += usage.get("totalTokens", 0)
                            if "cost" in usage:
                                result["cost"] += usage["cost"].get("total", 0)
                        # Модель и провайдер из message
                        if "provider" in msg:
                            result["provider"] = msg["provider"]
                        if "model" in msg:
                            result["model"] = msg["model"]
                        # Считаем сообщения
                        if msg.get("role") in ["user", "assistant"]:
                            result["messages"] += 1
                    
                    # Извлекаем метаданные (приоритет верхнему уровню)
                    if "provider" in data:
                        result["provider"] = data["provider"]
                    if "model" in data:
                        result["model"] = data["model"]
                    if "modelId" in data and result["model"] is None:
                        result["model"] = data["modelId"]
                    
                    # Timestamp (миллисекунды или ISO строка)
                    if "timestamp" in data and result["timestamp"] is None:
                        result["timestamp"] = data["timestamp"]
                        
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    
    return result


def get_all_sessions() -> list[dict]:
    """Получить статистику всех сессий."""
    files = find_session_files()
    sessions = []
    for f in files:
        session = parse_session_file(f)
        if session["tokens"] > 0 or session["messages"] > 0:
            sessions.append(session)
    return sessions


@app.command()
def summary():
    """Общая сводка по использованию токенов."""
    sessions = get_all_sessions()
    
    if not sessions:
        console.print("[yellow]Сессии не найдены[/yellow]")
        return
    
    total_tokens = sum(s["tokens"] for s in sessions)
    total_cost = sum(s["cost"] for s in sessions)
    total_messages = sum(s["messages"] for s in sessions)
    
    # Топ модели
    models = defaultdict(lambda: {"tokens": 0, "sessions": 0})
    for s in sessions:
        if s["model"]:
            models[s["model"]]["tokens"] += s["tokens"]
            models[s["model"]]["sessions"] += 1
    
    # Вывод
    console.print(Panel.fit(
        f"[bold cyan]OpenClaw Token Analyzer[/bold cyan]\n\n"
        f"📊 Всего сессий: [green]{len(sessions)}[/green]\n"
        f"📝 Всего сообщений: [green]{total_messages:,}[/green]\n"
        f"🎯 Всего токенов: [green]{total_tokens:,}[/green]\n"
        f"💰 Общая стоимость: [green]${total_cost:.4f}[/green]",
        title="Сводка"
    ))
    
    # Таблица моделей
    if models:
        table = Table(title="Топ моделей")
        table.add_column("Модель", style="cyan")
        table.add_column("Сессии", justify="right")
        table.add_column("Токены", justify="right")
        
        for model, data in sorted(models.items(), key=lambda x: x[1]["tokens"], reverse=True)[:10]:
            table.add_row(model, str(data["sessions"]), f"{data['tokens']:,}")
        
        console.print(table)


@app.command()
def by_agent():
    """Статистика по агентам."""
    sessions = get_all_sessions()
    
    if not sessions:
        console.print("[yellow]Сессии не найдены[/yellow]")
        return
    
    # Группировка по агентам
    agents = defaultdict(lambda: {"tokens": 0, "cost": 0.0, "sessions": 0})
    for s in sessions:
        agents[s["agent"]]["tokens"] += s["tokens"]
        agents[s["agent"]]["cost"] += s["cost"]
        agents[s["agent"]]["sessions"] += 1
    
    table = Table(title="Статистика по агентам")
    table.add_column("Агент", style="cyan")
    table.add_column("Сессии", justify="right")
    table.add_column("Токены", justify="right")
    table.add_column("Стоимость", justify="right")
    
    for agent, data in sorted(agents.items(), key=lambda x: x[1]["tokens"], reverse=True):
        table.add_row(
            agent,
            str(data["sessions"]),
            f"{data['tokens']:,}",
            f"${data['cost']:.4f}"
        )
    
    console.print(table)


@app.command()
def by_day():
    """Статистика по дням."""
    sessions = get_all_sessions()
    
    if not sessions:
        console.print("[yellow]Сессии не найдены[/yellow]")
        return
    
    # Группировка по дням
    days = defaultdict(lambda: {"tokens": 0, "cost": 0.0, "sessions": 0})
    for s in sessions:
        if s["timestamp"]:
            try:
                dt = datetime.fromtimestamp(s["timestamp"] / 1000)
                day = dt.strftime("%Y-%m-%d")
                days[day]["tokens"] += s["tokens"]
                days[day]["cost"] += s["cost"]
                days[day]["sessions"] += 1
            except:
                pass
    
    table = Table(title="Статистика по дням")
    table.add_column("Дата", style="cyan")
    table.add_column("Сессии", justify="right")
    table.add_column("Токены", justify="right")
    table.add_column("Стоимость", justify="right")
    
    for day, data in sorted(days.items(), reverse=True):
        table.add_row(
            day,
            str(data["sessions"]),
            f"{data['tokens']:,}",
            f"${data['cost']:.4f}"
        )
    
    console.print(table)


@app.command()
def top_sessions(limit: int = 10):
    """Топ сессий по использованию токенов."""
    sessions = get_all_sessions()
    
    if not sessions:
        console.print("[yellow]Сессии не найдены[/yellow]")
        return
    
    # Сортировка по токенам
    top = sorted(sessions, key=lambda x: x["tokens"], reverse=True)[:limit]
    
    table = Table(title=f"Топ {limit} сессий")
    table.add_column("Агент", style="cyan")
    table.add_column("Сессия", style="dim")
    table.add_column("Модель")
    table.add_column("Токены", justify="right")
    table.add_column("Стоимость", justify="right")
    
    for s in top:
        table.add_row(
            s["agent"],
            s["session_id"][:8] + "...",
            s["model"] or "-",
            f"{s['tokens']:,}",
            f"${s['cost']:.4f}"
        )
    
    console.print(table)


if __name__ == "__main__":
    app()
