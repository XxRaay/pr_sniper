import asyncio
import aiohttp
import json
from aiogram import Bot, Dispatcher, F, types, exceptions
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

# === Конфигурация ===
BOT_TOKEN = "Your_bot_token"
CHAT_ID = Your_chat_id
REPO = "Your_repo"
POLL_INTERVAL = 60  # интервал проверки GitHub в секундах

# Файлы для кеша
PR_STATES_FILE = "pr_states.json"
SETTINGS_FILE = "settings.json"

# === Глобальные переменные ===
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)
dp = Dispatcher()

# Храним состояния PR и настройки
pr_states: dict[str, str] = {}
settings: dict[str, str] = {"filter": "merged"}  # merged|open|closed


# === Работа с JSON ===
def load_json(path: str, default: dict) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# === GitHub API ===
async def fetch_prs(session: aiohttp.ClientSession, state="all") -> list[dict]:
    url = f"https://api.github.com/repos/{REPO}/pulls?state={state}"
    async with session.get(url) as resp:
        if resp.status != 200:
            print("GitHub API error:", resp.status, await resp.text())
            return []
        return await resp.json()


async def fetch_pr_by_number(session: aiohttp.ClientSession, number: int) -> dict | None:
    url = f"https://api.github.com/repos/{REPO}/pulls/{number}"
    async with session.get(url) as resp:
        if resp.status != 200:
            return None
        return await resp.json()


# === Логика состояний PR ===
def determine_state(pr: dict) -> str:
    if pr.get("merged_at"):
        return "merged"
    return pr.get("state", "unknown")


def format_pr(pr: dict) -> str:
    number = pr["number"]
    title = pr["title"]
    body = pr.get("body") or "_нет описания_"
    url = pr["html_url"]
    state = determine_state(pr)

    text = f"*PR #{number}:* [{title}]({url})\n"
    text += f"Статус: `{state}`\n"
    text += f"Описание:\n{body[:500]}"
    return text


# === Telegram команды ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот-наблюдатель за PR.\n\n"
        "Доступные команды:\n"
        "`/check <номер>` – проверить конкретный PR\n"
        "`/filter` – выбрать фильтр (open/closed/merged)\n"
        "`/state` – показать текущий фильтр"
    )


@dp.message(Command("state"))
async def cmd_state(message: Message):
    await message.answer(f"Текущий фильтр: *{settings['filter']}*")


@dp.message(Command("filter"))
async def cmd_filter(message: Message):
    kb = [
        [types.InlineKeyboardButton(text="Open", callback_data="filter_open")],
        [types.InlineKeyboardButton(text="Closed", callback_data="filter_closed")],
        [types.InlineKeyboardButton(text="Merged", callback_data="filter_merged")],
    ]
    await message.answer("Выберите фильтр:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data.startswith("filter_"))
async def cq_filter(query: types.CallbackQuery):
    val = query.data.split("_", 1)[1]
    settings["filter"] = val
    save_json(SETTINGS_FILE, settings)
    await query.answer()
    await query.message.edit_text(f"Фильтр установлен: *{val}*")


@dp.message(Command("check"))
async def cmd_check(message: Message):
    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: `/check <номер>`")
        return

    number = int(parts[1])
    async with aiohttp.ClientSession() as s:
        pr = await fetch_pr_by_number(s, number)
        if not pr:
            await message.answer(f"PR #{number} не найден")
            return
        await message.answer(format_pr(pr))


# === Фоновая задача ===
async def monitor_task(app_ctx: dict):
    session: aiohttp.ClientSession = app_ctx["gh_session"]
    while True:
        try:
            prs = await fetch_prs(session, "all")
            for pr in prs:
                num = str(pr["number"])
                state = determine_state(pr)
                prev_state = pr_states.get(num)

                # Сохраняем новое состояние
                pr_states[num] = state

                # Если новый merge — отправляем
                if prev_state != "merged" and state == "merged":
                    if settings.get("filter") == "merged":
                        try:
                            await bot.send_message(CHAT_ID, format_pr(pr))
                        except exceptions.TelegramAPIError as e:
                            print("Telegram send error:", e)

            save_json(PR_STATES_FILE, pr_states)
        except Exception as e:
            print("Monitor error:", e)

        await asyncio.sleep(POLL_INTERVAL)


# === Точка входа ===
async def main():
    global pr_states, settings

    # Загружаем кеш
    pr_states = load_json(PR_STATES_FILE, {})
    settings = load_json(SETTINGS_FILE, {"filter": "merged"})

    # Создаём HTTP-сессию для GitHub
    gh_session = aiohttp.ClientSession()
    app_ctx = {"gh_session": gh_session}

    # Запускаем мониторинг в фоне
    monitor = asyncio.create_task(monitor_task(app_ctx))

    try:
        await dp.start_polling(bot)
    finally:
        monitor.cancel()
        try:
            await monitor
        except asyncio.CancelledError:
            pass
        await gh_session.close()
        save_json(PR_STATES_FILE, pr_states)
        save_json(SETTINGS_FILE, settings)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
