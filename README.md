# GitHub PR Sniper Bot

Telegram-бот на базе [aiogram 3](https://github.com/aiogram/aiogram), который отслеживает Pull Request'ы в GitHub-репозитории и уведомляет о новых merge.

## Возможности
- Отслеживание PR'ов в указанном репозитории
- Уведомления о merge (по умолчанию)
- Фильтры: `open` / `closed` / `merged`
- Проверка конкретного PR по номеру
- Хранение состояния в JSON

## Запуск

git clone https://github.com/XxRaay/pr-sniper.git
cd pr-sniper

# Установка окружения
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Запуск
python bot.py
# pr_sniper
