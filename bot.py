import os
import logging
import asyncio
import httpx

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

users = set()
channels = {}  # {chat_id: {"username": "@xxx", "title": "..."}}


class AddChannel(StatesGroup):
    waiting_username = State()


def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="admin_add")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="admin_list")],
        [InlineKeyboardButton(text="➖ Kanal o'chirish", callback_data="admin_remove")],
    ])


async def ask_gemini(prompt: str) -> str:
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "content-type": "application/json",
    }
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GEMINI_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def missing_subscriptions(user_id: int):
    missing = []
    for chat_id, info in channels.items():
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                missing.append(info)
        except Exception as e:
            logging.error(f"Obuna tekshirishda xato ({chat_id}): {e}")
    return missing


def subscribe_kb(missing):
    buttons = [[InlineKeyboardButton(text=info["title"], url=f"https://t.me/{info['username'].lstrip('@')}")] for info in missing]
    buttons.append([InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("start"))
async def start_handler(message: Message):
    users.add(message.from_user.id)
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "Men ism ma'nosini aytib beruvchi botman.\n"
        "Menga istalgan ismni yuboring — men uning ma'nosini aytib beraman.\n\n"
        "Masalan: <b>Ravshan</b>"
    )


@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛠 Admin panel", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "admin_add")
async def admin_add_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer(
        "Kanal usernameni yuboring (masalan: @mening_kanalim).\n"
        "⚠️ Bot o'sha kanalda ADMIN bo'lishi shart!"
    )
    await state.set_state(AddChannel.waiting_username)
    await callback.answer()


@dp.callback_query(F.data == "admin_list")
async def admin_list_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    if not channels:
        await callback.message.answer("Hozircha kanallar yo'q.")
    else:
        text = "📋 Majburiy obuna kanallari:\n\n" + "\n".join(
            f"• {info['title']} ({info['username']})" for info in channels.values()
        )
        await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data == "admin_remove")
async def admin_remove_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    if not channels:
        await callback.message.answer("O'chirish uchun kanal yo'q.")
        await callback.answer()
        return
    buttons = [[InlineKeyboardButton(text=info["title"], callback_data=f"remove_{chat_id}")] for chat_id, info in channels.items()]
    await callback.message.answer("O'chirmoqchi bo'lgan kanalni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@dp.callback_query(F.data.startswith("remove_"))
async def remove_channel_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    chat_id = int(callback.data.split("_", 1)[1])
    removed = channels.pop(chat_id, None)
    if removed:
        await callback.message.answer(f"🗑 O'chirildi: {removed['title']}")
    await callback.answer()


@dp.callback_query(F.data == "check_sub")
async def check_sub_cb(callback: CallbackQuery):
    missing = await missing_subscriptions(callback.from_user.id)
    if missing:
        await callback.answer("Hali barcha kanallarga obuna bo'lmagansiz ❌", show_alert=True)
    else:
        await callback.message.edit_text("✅ Rahmat! Endi ism yuborishingiz mumkin.")
        await callback.answer()


@dp.message(Command("stats"))
async def stats_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"👥 Foydalanuvchilar soni: {len(users)}")


@dp.message(AddChannel.waiting_username)
async def admin_add_process(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    username = message.text.strip()
    try:
        chat = await bot.get_chat(username)
        channels[chat.id] = {"username": username, "title": chat.title}
        await message.answer(f"✅ Qo'shildi: {chat.title}")
    except Exception as e:
        await message.answer(f"❌ Xatolik: kanal topilmadi yoki bot u yerda admin emas.\n{e}")
    await state.clear()


@dp.message(F.text)
async def name_handler(message: Message):
    users.add(message.from_user.id)

    # Admin uchun: erkin sun'iy intellekt suhbati
    if message.from_user.id == ADMIN_ID:
        thinking_msg = await message.answer("🤖 O'ylayapman...")
        try:
            answer = await ask_gemini(message.text)
            await thinking_msg.edit_text(answer)
        except Exception as e:
            logging.error(f"Xatolik: {e}")
            await thinking_msg.edit_text("Xatolik yuz berdi.")
        return

    # Oddiy foydalanuvchilar uchun: majburiy obuna tekshiruvi
    missing = await missing_subscriptions(message.from_user.id)
    if missing:
        await message.answer(
            "Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling:",
            reply_markup=subscribe_kb(missing),
        )
        return

    name = message.text.strip()
    if len(name) > 30 or not name.replace(" ", "").isalpha():
        await message.answer("Iltimos, faqat ism yuboring 🙂")
        return

    thinking_msg = await message.answer("🔎 Qidiryapman...")
    try:
        meaning = await ask_gemini(
            f"'{name}' ismining ma'nosi, kelib chiqishi va xarakteri haqida "
            "o'zbek tilida qisqa, chiroyli va iliq uslubda yoz. "
            "4-5 gapdan oshmasin. Emoji ishlatsang bo'ladi."
        )
        await thinking_msg.edit_text(f"✨ <b>{name}</b>\n\n{meaning}")
    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await thinking_msg.edit_text("Kechirasiz, xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
