import os
import json
import asyncio
import logging
import httpx

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

MAIN_BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
DATA_FILE = "bots_data.json"

logging.basicConfig(level=logging.INFO)

main_bot = Bot(token=MAIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
main_dp = Dispatcher(storage=MemoryStorage())

BOT_TYPES = {
    "kino": "🎬 Kino bot",
    "quiz": "🧠 Viktorina bot",
    "shop": "🛒 Buyurtma bot",
    "ai": "🤖 AI-yordamchi bot",
    "post": "📢 E'lon/Xabar bot",
}

running_bots = {}  # token -> asyncio task


# ---------- Ma'lumotlarni saqlash ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"bots": {}}


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


data = load_data()


# ---------- Gemini yordamchisi ----------
async def ask_gemini(prompt: str) -> str:
    headers = {"x-goog-api-key": GEMINI_API_KEY, "content-type": "application/json"}
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GEMINI_URL, headers=headers, json=payload)
        resp.raise_for_status()
        result = resp.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]


# ---------- Bosh (creator) bot ----------
class NewBotFlow(StatesGroup):
    waiting_token = State()


def types_kb():
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"type_{key}")] for key, name in BOT_TYPES.items()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@main_dp.message(Command("myid"))
async def myid_handler(message: Message):
    await message.answer(f"Sizning Telegram ID'ingiz: <code>{message.from_user.id}</code>")


@main_dp.message(Command("start"))
async def main_start(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(
            "👋 Assalomu alaykum!\n\nBu — bot yaratuvchi tizim. Hozircha bu yerda siz uchun maxsus funksiya yo'q."
        )
        return
    await message.answer(
        "🤖 <b>Bot yaratuvchi botga xush kelibsiz!</b>\n\n"
        "Yangi bot yaratish uchun /newbot buyrug'ini yuboring.\n"
        "Mavjud botlaringizni ko'rish uchun /mybots."
    )


@main_dp.message(Command("newbot"))
async def newbot_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "Yangi bot tokenini yuboring.\n"
        "(@BotFather orqali /newbot bilan yaratib, tokenni shu yerga joylashtiring)"
    )
    await state.set_state(NewBotFlow.waiting_token)


@main_dp.message(NewBotFlow.waiting_token)
async def newbot_token(message: Message, state: FSMContext):
    token = message.text.strip()
    try:
        test_bot = Bot(token=token)
        me = await test_bot.get_me()
        await test_bot.session.close()
    except Exception:
        await message.answer("❌ Token noto'g'ri. Qaytadan yuboring.")
        return

    await state.update_data(token=token, bot_name=me.first_name)
    await message.answer(f"✅ Bot topildi: <b>{me.first_name}</b>\n\nEndi turini tanlang:", reply_markup=types_kb())


@main_dp.callback_query(F.data.startswith("type_"))
async def newbot_type(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    bot_type = callback.data.split("_", 1)[1]
    state_data = await state.get_data()
    token = state_data.get("token")
    bot_name = state_data.get("bot_name")

    if not token:
        await callback.answer("Xatolik: token topilmadi, qaytadan /newbot bosing.", show_alert=True)
        return

    data["bots"][token] = {"type": bot_type, "name": bot_name, "movies": {}, "users": []}
    save_data()

    await start_child_bot(token, bot_type)

    await callback.message.edit_text(f"✅ {BOT_TYPES[bot_type]} ishga tushdi: <b>{bot_name}</b>")
    await state.clear()
    await callback.answer()


@main_dp.message(Command("mybots"))
async def mybots(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not data["bots"]:
        await message.answer("Hali botlar yo'q. /newbot orqali yarating.")
        return
    text = "🤖 <b>Sizning botlaringiz:</b>\n\n"
    for token, info in data["bots"].items():
        status = "🟢" if token in running_bots else "🔴"
        text += f"{status} {info['name']} — {BOT_TYPES.get(info['type'], info['type'])}\n"
    await message.answer(text)


# ---------- Kino bot ----------
def setup_kino_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]

    @dp.message(Command("start"))
    async def kstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        await message.answer("🎬 Film kodini yuboring, men uni topib beraman.")

    @dp.message(F.video)
    async def save_movie(message: Message):
        if message.from_user.id != ADMIN_ID:
            return
        code = (message.caption or "").strip()
        if not code:
            await message.answer("❌ Video caption'iga kod yozing (masalan: 101)")
            return
        info["movies"][code] = message.video.file_id
        save_data()
        await message.answer(f"✅ Kod {code} bilan saqlandi.")

    @dp.message(F.text)
    async def get_movie(message: Message):
        code = message.text.strip()
        file_id = info["movies"].get(code)
        if file_id:
            await message.answer_video(file_id, caption=f"🎬 Kod: {code}")
        else:
            await message.answer("❌ Bunday kodli film topilmadi.")


# ---------- Viktorina bot ----------
QUIZ_QUESTIONS = [
    {"q": "O'zbekiston poytaxti?", "options": ["Samarqand", "Toshkent", "Buxoro"], "correct": 1},
    {"q": "2 + 2 nechiga teng?", "options": ["3", "4", "5"], "correct": 1},
    {"q": "Eng katta okean?", "options": ["Tinch okean", "Atlantika", "Hind okeani"], "correct": 0},
]


def setup_quiz_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]

    async def send_question(message: Message, idx: int):
        if idx >= len(QUIZ_QUESTIONS):
            await message.answer("🎉 Test tugadi! Qaytadan boshlash uchun /start bosing.")
            return
        q = QUIZ_QUESTIONS[idx]
        buttons = [[InlineKeyboardButton(text=opt, callback_data=f"quiz_{idx}_{i}")] for i, opt in enumerate(q["options"])]
        await message.answer(q["q"], reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    @dp.message(Command("start"))
    async def qstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        await send_question(message, 0)

    @dp.callback_query(F.data.startswith("quiz_"))
    async def quiz_answer(callback: CallbackQuery):
        _, idx, choice = callback.data.split("_")
        idx, choice = int(idx), int(choice)
        correct = QUIZ_QUESTIONS[idx]["correct"]
        await callback.answer("✅ To'g'ri!" if choice == correct else "❌ Noto'g'ri!")
        await send_question(callback.message, idx + 1)


# ---------- Buyurtma bot ----------
def setup_shop_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]

    @dp.message(Command("start"))
    async def sstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        await message.answer(
            "🛒 Buyurtma botiga xush kelibsiz!\n\nBuyurtma bermoqchi bo'lgan mahsulot nomini yozing."
        )

    @dp.message(F.text)
    async def order(message: Message):
        username = message.from_user.username or message.from_user.id
        await main_bot.send_message(
            ADMIN_ID,
            f"🛒 <b>Yangi buyurtma!</b>\nBot: {info['name']}\n"
            f"Foydalanuvchi: @{username}\nXabar: {message.text}",
        )
        await message.answer("✅ Buyurtmangiz qabul qilindi!")


# ---------- AI-yordamchi bot ----------
def setup_ai_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]

    @dp.message(Command("start"))
    async def astart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        await message.answer("🤖 Menga istalgan savolni yozing!")

    @dp.message(F.text)
    async def ai_chat(message: Message):
        thinking = await message.answer("💭 O'ylayapman...")
        try:
            answer = await ask_gemini(message.text)
            await thinking.edit_text(answer)
        except Exception as e:
            logging.error(f"Xatolik: {e}")
            await thinking.edit_text("Xatolik yuz berdi.")


# ---------- E'lon/Xabar bot ----------
class PostFlow(StatesGroup):
    waiting_text = State()


def setup_post_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]

    @dp.message(Command("start"))
    async def pstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        await message.answer("📢 Yangiliklarga obuna bo'ldingiz!")

    @dp.message(Command("post"))
    async def post_cmd(message: Message, state: FSMContext):
        if message.from_user.id != ADMIN_ID:
            return
        await message.answer("E'lon matnini yuboring, u barcha obunachilarga yuboriladi.")
        await state.set_state(PostFlow.waiting_text)

    @dp.message(PostFlow.waiting_text)
    async def post_send(message: Message, state: FSMContext):
        count = 0
        for uid in info["users"]:
            try:
                await message.bot.send_message(uid, message.text)
                count += 1
            except Exception:
                pass
        await message.answer(f"✅ {count} ta foydalanuvchiga yuborildi.")
        await state.clear()


SETUP_FUNCTIONS = {
    "kino": setup_kino_bot,
    "quiz": setup_quiz_bot,
    "shop": setup_shop_bot,
    "ai": setup_ai_bot,
    "post": setup_post_bot,
}


async def start_child_bot(token: str, bot_type: str):
    if token in running_bots:
        return
    child_bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    child_dp = Dispatcher(storage=MemoryStorage())
    SETUP_FUNCTIONS[bot_type](child_dp, token)
    task = asyncio.create_task(child_dp.start_polling(child_bot))
    running_bots[token] = task


async def main():
    # Avval saqlangan botlarni qayta ishga tushiramiz
    for token, info in data["bots"].items():
        await start_child_bot(token, info["type"])

    await main_dp.start_polling(main_bot)


if __name__ == "__main__":
    asyncio.run(main())
