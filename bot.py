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
    "shop": "🛒 Savdo bot",
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


# ---------- Holatlar (FSM) ----------
class NewBotFlow(StatesGroup):
    waiting_token = State()
    waiting_admin = State()


class AddMovie(StatesGroup):
    waiting_code = State()
    waiting_video = State()


class AddProduct(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_qty = State()


class PostFlow(StatesGroup):
    waiting_text = State()
    waiting_confirm = State()


# ---------- Bosh (creator) bot ----------
def types_kb():
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"type_{key}")] for key, name in BOT_TYPES.items()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@main_dp.message(Command("myid"))
async def myid_handler(message: Message):
    await message.answer(f"Sizning Telegram ID'ingiz: <code>{message.from_user.id}</code>")


@main_dp.message(Command("start"))
async def main_start(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Bu bot faqat egasi uchun mo'ljallangan.")
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
    await message.answer(
        f"✅ Bot topildi: <b>{me.first_name}</b>\n\n"
        "Endi shu botning egasi (admin) bo'ladigan Telegram ID'ni yuboring.\n"
        "(O'zingizning ID'ingizni bilish uchun /myid dan foydalanishingiz mumkin)"
    )
    await state.set_state(NewBotFlow.waiting_admin)


@main_dp.message(NewBotFlow.waiting_admin)
async def newbot_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        return
    await state.update_data(admin_id=admin_id)
    await message.answer("Endi bot turini tanlang:", reply_markup=types_kb())


@main_dp.callback_query(F.data.startswith("type_"))
async def newbot_type(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    bot_type = callback.data.split("_", 1)[1]
    state_data = await state.get_data()
    token = state_data.get("token")
    bot_name = state_data.get("bot_name")
    admin_id = state_data.get("admin_id")

    if not token or admin_id is None:
        await callback.answer("Xatolik: qaytadan /newbot bosing.", show_alert=True)
        return

    data["bots"][token] = {
        "type": bot_type,
        "name": bot_name,
        "admin_id": admin_id,
        "movies": {},
        "products": {},
        "next_id": 1,
        "carts": {},
        "users": [],
    }
    save_data()

    await start_child_bot(token, bot_type)

    await callback.message.edit_text(
        f"✅ {BOT_TYPES[bot_type]} ishga tushdi: <b>{bot_name}</b>\nAdmin ID: {admin_id}"
    )
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
        text += f"{status} {info['name']} — {BOT_TYPES.get(info['type'], info['type'])} (admin: {info['admin_id']})\n"
    await message.answer(text)


# ---------- Kino bot ----------
def setup_kino_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]
    admin_id = info["admin_id"]

    @dp.message(Command("start"))
    async def kstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        if uid == admin_id:
            await message.answer(
                "🎬 <b>Kino bot boshqaruvi</b>\n\n"
                "Yangi film qo'shish uchun: /addmovie\n"
                "Foydalanuvchilar film kodini yuborsa, filmni topib beraman."
            )
        else:
            await message.answer("🎬 Film kodini yuboring, men uni topib beraman.")

    @dp.message(Command("addmovie"))
    async def addmovie_cmd(message: Message, state: FSMContext):
        if message.from_user.id != admin_id:
            return
        await message.answer("Kino kodini yuboring (masalan: 040):")
        await state.set_state(AddMovie.waiting_code)

    @dp.message(AddMovie.waiting_code)
    async def addmovie_code(message: Message, state: FSMContext):
        code = message.text.strip()
        await state.update_data(code=code)
        await message.answer(f"Endi <b>{code}</b> kodli filmni (videoni) yuboring:")
        await state.set_state(AddMovie.waiting_video)

    @dp.message(AddMovie.waiting_video, F.video)
    async def addmovie_video(message: Message, state: FSMContext):
        state_data = await state.get_data()
        code = state_data.get("code")
        info["movies"][code] = message.video.file_id
        save_data()
        await message.answer(f"✅ Kod <b>{code}</b> bilan film saqlandi.")
        await state.clear()

    @dp.message(AddMovie.waiting_video)
    async def addmovie_wrong(message: Message):
        await message.answer("❌ Iltimos, video fayl yuboring (forward qilingan bo'lsa ham bo'ladi).")

    @dp.message(F.text)
    async def get_movie(message: Message):
        code = message.text.strip()
        file_id = info["movies"].get(code)
        if file_id:
            await message.answer_video(file_id, caption=f"🎬 Kod: {code}")
        else:
            await message.answer("❌ Bunday kodli film topilmadi.")


# ---------- Savdo bot ----------
def setup_shop_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]
    admin_id = info["admin_id"]

    def admin_kb():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Mahsulot qo'shish", callback_data="padd")],
            [InlineKeyboardButton(text="📦 Mahsulotlar ro'yxati", callback_data="plist")],
            [InlineKeyboardButton(text="➖ Mahsulotni o'chirish", callback_data="pdel")],
        ])

    def catalog_kb():
        buttons = []
        for pid, p in info["products"].items():
            if p["qty"] > 0:
                buttons.append([InlineKeyboardButton(text=f"{p['name']} — {p['price']:,} so'm", callback_data=f"buy_{pid}")])
        buttons.append([InlineKeyboardButton(text="🛒 Savatim", callback_data="cart")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @dp.message(Command("start"))
    async def sstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        if uid == admin_id:
            await message.answer("🛒 <b>Savdo bot boshqaruvi</b>", reply_markup=admin_kb())
        elif not info["products"]:
            await message.answer("Hozircha mahsulotlar yo'q.")
        else:
            await message.answer("🛍 Mahsulotlar:", reply_markup=catalog_kb())

    @dp.callback_query(F.data == "padd")
    async def padd_cb(callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id != admin_id:
            return
        await callback.message.answer("Mahsulot nomini yozing:")
        await state.set_state(AddProduct.waiting_name)
        await callback.answer()

    @dp.message(AddProduct.waiting_name)
    async def padd_name(message: Message, state: FSMContext):
        await state.update_data(name=message.text.strip())
        await message.answer("Narxini yozing (faqat raqam, so'mda):")
        await state.set_state(AddProduct.waiting_price)

    @dp.message(AddProduct.waiting_price)
    async def padd_price(message: Message, state: FSMContext):
        try:
            price = int(message.text.strip().replace(" ", ""))
        except ValueError:
            await message.answer("❌ Faqat raqam kiriting.")
            return
        await state.update_data(price=price)
        await message.answer("Sonini (nechta borligini) yozing:")
        await state.set_state(AddProduct.waiting_qty)

    @dp.message(AddProduct.waiting_qty)
    async def padd_qty(message: Message, state: FSMContext):
        try:
            qty = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Faqat raqam kiriting.")
            return
        state_data = await state.get_data()
        pid = str(info["next_id"])
        info["next_id"] += 1
        info["products"][pid] = {"name": state_data["name"], "price": state_data["price"], "qty": qty}
        save_data()
        await message.answer(f"✅ Qo'shildi: {state_data['name']} — {state_data['price']:,} so'm ({qty} dona)")
        await state.clear()

    @dp.callback_query(F.data == "plist")
    async def plist_cb(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            return
        if not info["products"]:
            await callback.message.answer("Mahsulotlar yo'q.")
        else:
            text = "📦 <b>Mahsulotlar:</b>\n\n" + "\n".join(
                f"#{pid}: {p['name']} — {p['price']:,} so'm ({p['qty']} dona)" for pid, p in info["products"].items()
            )
            await callback.message.answer(text)
        await callback.answer()

    @dp.callback_query(F.data == "pdel")
    async def pdel_cb(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            return
        if not info["products"]:
            await callback.message.answer("O'chirish uchun mahsulot yo'q.")
            await callback.answer()
            return
        buttons = [[InlineKeyboardButton(text=p["name"], callback_data=f"pdelid_{pid}")] for pid, p in info["products"].items()]
        await callback.message.answer("O'chirmoqchi bo'lgan mahsulotni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()

    @dp.callback_query(F.data.startswith("pdelid_"))
    async def pdelid_cb(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            return
        pid = callback.data.split("_", 1)[1]
        removed = info["products"].pop(pid, None)
        save_data()
        if removed:
            await callback.message.answer(f"🗑 O'chirildi: {removed['name']}")
        await callback.answer()

    @dp.callback_query(F.data.startswith("buy_"))
    async def buy_cb(callback: CallbackQuery):
        pid = callback.data.split("_", 1)[1]
        uid = str(callback.from_user.id)
        product = info["products"].get(pid)
        if not product or product["qty"] <= 0:
            await callback.answer("❌ Mahsulot tugagan.", show_alert=True)
            return
        cart = info["carts"].setdefault(uid, {})
        cart[pid] = cart.get(pid, 0) + 1
        save_data()
        total = sum(info["products"][p]["price"] * q for p, q in cart.items() if p in info["products"])
        await callback.answer(f"✅ Qo'shildi! Savat: {total:,} so'm")

    @dp.callback_query(F.data == "cart")
    async def cart_cb(callback: CallbackQuery):
        uid = str(callback.from_user.id)
        cart = info["carts"].get(uid, {})
        if not cart:
            await callback.message.answer("🛒 Savatingiz bo'sh.")
            await callback.answer()
            return
        lines = []
        total = 0
        for pid, qty in cart.items():
            p = info["products"].get(pid)
            if not p:
                continue
            subtotal = p["price"] * qty
            total += subtotal
            lines.append(f"{p['name']} x{qty} = {subtotal:,} so'm")
        text = "🛒 <b>Savatingiz:</b>\n\n" + "\n".join(lines) + f"\n\n💰 Jami: {total:,} so'm"
        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="checkout")],
            [InlineKeyboardButton(text="🗑 Tozalash", callback_data="cart_clear")],
        ])
        await callback.message.answer(text, reply_markup=buttons)
        await callback.answer()

    @dp.callback_query(F.data == "cart_clear")
    async def cart_clear_cb(callback: CallbackQuery):
        uid = str(callback.from_user.id)
        info["carts"][uid] = {}
        save_data()
        await callback.message.answer("🗑 Savat tozalandi.")
        await callback.answer()

    @dp.callback_query(F.data == "checkout")
    async def checkout_cb(callback: CallbackQuery):
        uid = str(callback.from_user.id)
        cart = info["carts"].get(uid, {})
        if not cart:
            await callback.answer("Savat bo'sh.", show_alert=True)
            return
        lines = []
        total = 0
        for pid, qty in cart.items():
            p = info["products"].get(pid)
            if not p:
                continue
            subtotal = p["price"] * qty
            total += subtotal
            lines.append(f"{p['name']} x{qty} = {subtotal:,} so'm")
            p["qty"] = max(0, p["qty"] - qty)
        username = callback.from_user.username or callback.from_user.id
        text = f"🛒 <b>Yangi buyurtma!</b>\nXaridor: @{username}\n\n" + "\n".join(lines) + f"\n\n💰 Jami: {total:,} so'm"
        await callback.bot.send_message(admin_id, text)
        info["carts"][uid] = {}
        save_data()
        await callback.message.answer("✅ Buyurtmangiz qabul qilindi! Tez orada bog'lanishadi.")
        await callback.answer()


# ---------- AI-yordamchi bot ----------
def setup_ai_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]

    @dp.message(Command("start"))
    async def astart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        await message.answer("🤖 Salom! Menga istalgan savolni yozing, sun'iy intellekt sifatida javob beraman.")

    @dp.message(F.text)
    async def ai_chat(message: Message):
        await message.bot.send_chat_action(message.chat.id, "typing")
        thinking = await message.answer("💭 O'ylayapman...")
        try:
            answer = await ask_gemini(message.text)
            await thinking.edit_text(answer)
        except Exception as e:
            logging.error(f"Xatolik: {e}")
            await thinking.edit_text("Xatolik yuz berdi, birozdan keyin qayta urinib ko'ring.")


# ---------- E'lon/Xabar bot ----------
def setup_post_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]
    admin_id = info["admin_id"]

    def admin_kb():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="newpost")],
            [InlineKeyboardButton(text="👥 Obunachilar soni", callback_data="substats")],
        ])

    @dp.message(Command("start"))
    async def pstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        if uid == admin_id:
            await message.answer("📢 <b>E'lon bot boshqaruvi</b>", reply_markup=admin_kb())
        else:
            await message.answer("📢 Yangiliklarga obuna bo'ldingiz!")

    @dp.callback_query(F.data == "substats")
    async def substats_cb(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            return
        await callback.message.answer(f"👥 Obunachilar soni: {len(info['users'])}")
        await callback.answer()

    @dp.callback_query(F.data == "newpost")
    async def newpost_cb(callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id != admin_id:
            return
        await callback.message.answer("E'lon matnini yuboring:")
        await state.set_state(PostFlow.waiting_text)
        await callback.answer()

    @dp.message(PostFlow.waiting_text)
    async def post_text(message: Message, state: FSMContext):
        await state.update_data(text=message.text)
        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Yuborish", callback_data="post_confirm")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="post_cancel")],
        ])
        await message.answer(
            f"Quyidagi xabar {len(info['users'])} kishiga yuborilsinmi?\n\n{message.text}",
            reply_markup=buttons,
        )
        await state.set_state(PostFlow.waiting_confirm)

    @dp.callback_query(F.data == "post_confirm", PostFlow.waiting_confirm)
    async def post_confirm_cb(callback: CallbackQuery, state: FSMContext):
        state_data = await state.get_data()
        text = state_data.get("text", "")
        count = 0
        for uid in info["users"]:
            try:
                await callback.bot.send_message(uid, text)
                count += 1
            except Exception:
                pass
        await callback.message.edit_text(f"✅ {count} ta foydalanuvchiga yuborildi.")
        await state.clear()
        await callback.answer()

    @dp.callback_query(F.data == "post_cancel", PostFlow.waiting_confirm)
    async def post_cancel_cb(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_text("❌ Bekor qilindi.")
        await state.clear()
        await callback.answer()


SETUP_FUNCTIONS = {
    "kino": setup_kino_bot,
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
    for token, info in data["bots"].items():
        await start_child_bot(token, info["type"])

    await main_dp.start_polling(main_bot)


if __name__ == "__main__":
    asyncio.run(main())
