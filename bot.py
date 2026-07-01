import os
import logging
import asyncio
import httpx

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- Railway'da Variables bo'limiga qo'shiladigan sozlamalar ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # sizning Telegram ID'ingiz

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Foydalanuvchilarni eslab turish (statistika uchun, oddiy xotira)
users = set()


async def ask_claude(name: str) -> str:
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 400,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"'{name}' ismining ma'nosi, kelib chiqishi va xarakteri haqida "
                    "o'zbek tilida qisqa, chiroyli va iliq uslubda yoz. "
                    "4-5 gapdan oshmasin. Emoji ishlatsang bo'ladi."
                ),
            }
        ],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages", headers=headers, json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


@dp.message(Command("start"))
async def start_handler(message: Message):
    users.add(message.from_user.id)
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "Men ism ma'nosini aytib beruvchi botman.\n"
        "Menga istalgan ismni yuboring — men uning ma'nosini aytib beraman.\n\n"
        "Masalan: <b>Ravshan</b>"
    )


@dp.message(Command("stats"))
async def stats_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"👥 Foydalanuvchilar soni: {len(users)}")


@dp.message(F.text)
async def name_handler(message: Message):
    users.add(message.from_user.id)
    name = message.text.strip()

    if len(name) > 30 or not name.replace(" ", "").isalpha():
        await message.answer("Iltimos, faqat ism yuboring 🙂")
        return

    thinking_msg = await message.answer("🔎 Qidiryapman...")
    try:
        meaning = await ask_claude(name)
        await thinking_msg.edit_text(f"✨ <b>{name}</b>\n\n{meaning}")
    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await thinking_msg.edit_text(
            "Kechirasiz, xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring."
        )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main()) 
