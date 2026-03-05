# OpenClaw Token Analyzer

CLI утилита для анализа использования токенов в OpenClaw сессиях.

## Установка

```bash
cd ~/.openclaw/workspace/tools/token-analyzer
pip install -r requirements.txt
```

## Использование

```bash
python analyzer.py --help
```

### Команды

| Команда | Описание |
|---------|----------|
| `summary` | Общая сводка по токенам |
| `by-agent` | Статистика по агентам |
| `by-day` | Статистика по дням |
| `top-sessions` | Топ сессий по токенам |

### Примеры

```bash
# Общая сводка
python analyzer.py summary

# Статистика по агентам
python analyzer.py by-agent

# Топ 20 сессий
python analyzer.py top-sessions --limit 20
```
