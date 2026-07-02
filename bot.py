import os
import json
import asyncio
import logging
import httpx
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

MAIN_BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # bosh administrator (siz)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
DATA_FILE = "bots_data.json"
TRIAL_DAYS = 7

logging.basicConfig(level=logging.INFO)

main_bot = Bot(token=MAIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
main_dp = Dispatcher(storage=MemoryStorage())

BOT_TYPES = {
    "kino": "🎬 Kino bot",
    "shop": "🛒 Savdo bot",
    "ai": "🤖 AI-yordamchi bot",
    "post": "📢 E'lon/Xabar bot",
}

PRICES = {
    "kino": 150_000,
    "ai": 100_000,
    "shop": 250_000,
    "post": 100_000,
}
MONTHLY_RATE = 0.2  # keyingi oylar uchun narxning 20 foizi

running_bots = {}


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"bots": {}, "next_bot_id": 1}


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


data = load_data()
data.setdefault("next_bot_id", 1)


def is_active(info: dict) -> bool:
    paid_until = info.get("paid_until")
    if paid_until and datetime.now() < datetime.fromisoformat(paid_until):
        return True
    created = datetime.fromisoformat(info["created_at"])
    return datetime.now() < created + timedelta(days=TRIAL_DAYS)


def next_payment_amount(info: dict) -> int:
    """Birinchi to'lov — to'liq narx. Keyingi to'lovlar — 20 foiz."""
    price = PRICES.get(info["type"], 0)
    if info.get("paid_until"):
        return int(price * MONTHLY_RATE)
    return price


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


class AddMovie(StatesGroup):
    waiting_code = State()
    waiting_desc = State()
    waiting_video = State()


class AddProduct(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_qty = State()


class Checkout(StatesGroup):
    waiting_address = State()
    waiting_phone = State()


class PostFlow(StatesGroup):
    waiting_text = State()
    waiting_confirm = State()


class AddChannel(StatesGroup):
    waiting_username = State()


# ---------- Majburiy obuna (barcha botlar uchun umumiy) ----------
def channels_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="ch_add")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="ch_list")],
        [InlineKeyboardButton(text="➖ Kanal o'chirish", callback_data="ch_del")],
    ])


async def get_missing_channels(bot: Bot, channels: dict, user_id: int):
    missing = []
    for chat_id, info in channels.items():
        try:
            member = await bot.get_chat_member(chat_id=int(chat_id), user_id=user_id)
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                missing.append(info)
        except Exception as e:
            logging.error(f"Obuna tekshirishda xato ({chat_id}): {e}")
    return missing


def subscribe_kb(missing):
    buttons = [[InlineKeyboardButton(text=info["title"], url=f"https://t.me/{info['username'].lstrip('@')}")] for info in missing]
    buttons.append([InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def require_subscription(event, info: dict, admin_id: int) -> bool:
    uid = event.from_user.id
    if uid == admin_id:
        return True
    channels = info.get("channels", {})
    if not channels:
        return True
    missing = await get_missing_channels(event.bot, channels, uid)
    if missing:
        kb = subscribe_kb(missing)
        text = "Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling:"
        if isinstance(event, CallbackQuery):
            await event.message.answer(text, reply_markup=kb)
            await event.answer()
        else:
            await event.answer(text, reply_markup=kb)
        return False
    return True


async def check_active(event, info: dict, admin_id: int) -> bool:
    """True bo'lsa - bot ishlaydi. False bo'lsa - sinov tugagan / to'lov kerak."""
    if is_active(info):
        return True
    uid = event.from_user.id
    amount = next_payment_amount(info)
    is_renewal = bool(info.get("paid_until"))
    if uid == admin_id:
        if is_renewal:
            text = (
                f"⏳ <b>Oylik to'lov muddati tugadi.</b>\n\n"
                f"Davom ettirish uchun: <b>{amount:,} so'm</b> (oylik, narxning 20%).\n\n"
                "To'lovni amalga oshirish uchun platforma administratoriga murojaat qiling."
            )
        else:
            text = (
                f"⏳ <b>Bepul sinov muddati tugadi.</b>\n\n"
                f"Ushbu bot ({BOT_TYPES.get(info['type'])}) boshlang'ich narxi: <b>{amount:,} so'm</b>.\n"
                f"Keyingi oylardan boshlab: {int(PRICES.get(info['type'], 0) * MONTHLY_RATE):,} so'm/oy.\n\n"
                "To'lovni amalga oshirish uchun platforma administratoriga murojaat qiling."
            )
    else:
        text = "🚧 Bot vaqtincha ishlamayapti."
    if isinstance(event, CallbackQuery):
        await event.message.answer(text)
        await event.answer()
    else:
        await event.answer(text)
    return False


def setup_subscription_handlers(dp: Dispatcher, token: str, admin_id: int):
    info = data["bots"][token]
    info.setdefault("channels", {})

    @dp.callback_query(F.data == "ch_add")
    async def ch_add_cb(callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id != admin_id:
            return
        await callback.message.answer(
            "Kanal usernameni yuboring (masalan: @mening_kanalim).\n"
            "⚠️ Bot o'sha kanalda ADMIN bo'lishi shart!"
        )
        await state.set_state(AddChannel.waiting_username)
        await callback.answer()

    @dp.message(AddChannel.waiting_username)
    async def ch_add_process(message: Message, state: FSMContext):
        if message.from_user.id != admin_id:
            return
        username = message.text.strip()
        try:
            chat = await message.bot.get_chat(username)
            info["channels"][str(chat.id)] = {"username": username, "title": chat.title}
            save_data()
            await message.answer(f"✅ Qo'shildi: {chat.title}")
        except Exception as e:
            await message.answer(f"❌ Xatolik: kanal topilmadi yoki bot u yerda admin emas.\n{e}")
        await state.clear()

    @dp.callback_query(F.data == "ch_list")
    async def ch_list_cb(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            return
        if not info["channels"]:
            await callback.message.answer("Hozircha majburiy kanallar yo'q.")
        else:
            text = "📋 Majburiy obuna kanallari:\n\n" + "\n".join(
                f"• {c['title']} ({c['username']})" for c in info["channels"].values()
            )
            await callback.message.answer(text)
        await callback.answer()

    @dp.callback_query(F.data == "ch_del")
    async def ch_del_cb(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            return
        if not info["channels"]:
            await callback.message.answer("O'chirish uchun kanal yo'q.")
            await callback.answer()
            return
        buttons = [[InlineKeyboardButton(text=c["title"], callback_data=f"chdel_{cid}")] for cid, c in info["channels"].items()]
        await callback.message.answer("O'chirmoqchi bo'lgan kanalni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()

    @dp.callback_query(F.data.startswith("chdel_"))
    async def ch_delid_cb(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            return
        cid = callback.data.split("_", 1)[1]
        removed = info["channels"].pop(cid, None)
        save_data()
        if removed:
            await callback.message.answer(f"🗑 O'chirildi: {removed['title']}")
        await callback.answer()

    @dp.callback_query(F.data == "check_sub")
    async def check_sub_cb(callback: CallbackQuery):
        missing = await get_missing_channels(callback.bot, info["channels"], callback.from_user.id)
        if missing:
            await callback.answer("Hali barcha kanallarga obuna bo'lmagansiz ❌", show_alert=True)
        else:
            await callback.message.edit_text("✅ Rahmat! Endi /start bosib davom eting.")
            await callback.answer()

    @dp.message(Command("channels"))
    async def channels_panel(message: Message):
        if message.from_user.id != admin_id:
            return
        await message.answer("📡 Majburiy obuna boshqaruvi:", reply_markup=channels_admin_kb())


# ---------- Bosh (creator) bot — XALQ UCHUN OMMAVIY ----------
def types_kb():
    buttons = [[InlineKeyboardButton(text=f"{name} — {PRICES[key]:,} so'm/oy", callback_data=f"type_{key}")] for key, name in BOT_TYPES.items()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@main_dp.message(Command("myid"))
async def myid_handler(message: Message):
    await message.answer(f"Sizning Telegram ID'ingiz: <code>{message.from_user.id}</code>")


@main_dp.message(Command("start"))
async def main_start(message: Message):
    text = (
        "🤖 <b>Bot yaratuvchi platformaga xush kelibsiz!</b>\n\n"
        "Bu yerda bir necha daqiqada o'zingizga kerakli botni yaratishingiz mumkin.\n\n"
        "💳 <b>Boshlang'ich narxlar:</b>\n"
        f"🎬 Kino bot — {PRICES['kino']:,} so'm\n"
        f"🤖 AI-yordamchi bot — {PRICES['ai']:,} so'm\n"
        f"🛒 Savdo bot — {PRICES['shop']:,} so'm\n"
        f"📢 E'lon/Xabar bot — {PRICES['post']:,} so'm\n\n"
        f"📅 Keyingi oylardan boshlab — narxning atigi {int(MONTHLY_RATE*100)}%.\n"
        f"🎁 Har bir bot uchun {TRIAL_DAYS} kunlik BEPUL sinov muddati bor!\n\n"
        "Bot yaratish: /newbot\n"
        "Botlaringiz: /mybots"
    )
    await message.answer(text)


@main_dp.message(Command("newbot"))
async def newbot_start(message: Message, state: FSMContext):
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
    await message.answer(f"✅ Bot topildi: <b>{me.first_name}</b>\n\nEndi bot turini tanlang:", reply_markup=types_kb())


@main_dp.callback_query(F.data.startswith("type_"))
async def newbot_type(callback: CallbackQuery, state: FSMContext):
    bot_type = callback.data.split("_", 1)[1]
    state_data = await state.get_data()
    token = state_data.get("token")
    bot_name = state_data.get("bot_name")

    if not token:
        await callback.answer("Xatolik: qaytadan /newbot bosing.", show_alert=True)
        return

    bot_id = data["next_bot_id"]
    data["next_bot_id"] += 1

    data["bots"][token] = {
        "id": bot_id,
        "type": bot_type,
        "name": bot_name,
        "admin_id": callback.from_user.id,
        "created_at": datetime.now().isoformat(),
        "paid_until": None,
        "movies": {},
        "products": {},
        "next_id": 1,
        "carts": {},
        "channels": {},
        "users": [],
        "stats": {},
    }
    save_data()

    await start_child_bot(token, bot_type)

    await callback.message.edit_text(
        f"✅ {BOT_TYPES[bot_type]} ishga tushdi: <b>{bot_name}</b>\n\n"
        f"🎁 {TRIAL_DAYS} kunlik bepul sinov boshlandi!\n"
        "Majburiy obuna qo'shish uchun o'sha botga /channels yozing."
    )
    await state.clear()
    await callback.answer()


@main_dp.message(Command("mybots"))
async def mybots(message: Message):
    uid = message.from_user.id
    if uid == ADMIN_ID:
        items = list(data["bots"].items())
    else:
        items = [(t, i) for t, i in data["bots"].items() if i["admin_id"] == uid]

    if not items:
        await message.answer("Hali botlaringiz yo'q. /newbot orqali yarating.")
        return

    for token, info in items:
        status = "🟢 Faol" if is_active(info) else "🔴 Sinov/to'lov tugagan"
        paid_until = info.get("paid_until")
        if paid_until:
            date_str = datetime.fromisoformat(paid_until).strftime("%d.%m.%Y")
            paid_note = f" (to'langan: {date_str} gacha)"
        else:
            paid_note = ""
        text = f"{BOT_TYPES.get(info['type'])}: <b>{info['name']}</b>\n{status}{paid_note}"
        if uid == ADMIN_ID and info["admin_id"] != ADMIN_ID:
            text += f"\n👤 Egasi ID: {info['admin_id']}"
        kb = None
        if uid == ADMIN_ID:
            amount = next_payment_amount(info)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"✅ To'lovni tasdiqlash ({amount:,} so'm)", callback_data=f"activate_{info['id']}")]
            ])
        await message.answer(text, reply_markup=kb)


@main_dp.callback_query(F.data.startswith("activate_"))
async def activate_cb(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    bot_id = int(callback.data.split("_", 1)[1])
    for token, info in data["bots"].items():
        if info.get("id") == bot_id:
            info["paid_until"] = (datetime.now() + timedelta(days=30)).isoformat()
            save_data()
            await callback.message.answer(f"✅ {info['name']} bot 30 kunga faollashtirildi.")
            break
    await callback.answer()


# ---------- Kino bot ----------
def setup_kino_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]
    admin_id = info["admin_id"]
    info["stats"].setdefault("requests", 0)
    setup_subscription_handlers(dp, token, admin_id)

    @dp.message(Command("start"))
    async def kstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        if not await check_active(message, info, admin_id):
            return
        if uid == admin_id:
            await message.answer(
                "🎬 <b>Kino bot boshqaruvi</b>\n\n"
                "Yangi film qo'shish: /addmovie\n"
                "Statistika: /stats\n"
                "Majburiy obuna: /channels\n\n"
                "Foydalanuvchilar film kodini yuborsa, filmni topib beraman."
            )
        else:
            await message.answer("🎬 Film kodini yuboring, men uni topib beraman.")

    @dp.message(Command("stats"))
    async def kino_stats(message: Message):
        if message.from_user.id != admin_id:
            return
        await message.answer(
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Foydalanuvchilar: {len(info['users'])}\n"
            f"🔍 Kino so'rovlari: {info['stats']['requests']}\n"
            f"🎞 Saqlangan filmlar: {len(info['movies'])}"
        )

    @dp.message(Command("addmovie"))
    async def addmovie_cmd(message: Message, state: FSMContext):
        if message.from_user.id != admin_id:
            return
        await message.answer("Kino kodini yuboring (faqat raqam, masalan: 40):")
        await state.set_state(AddMovie.waiting_code)

    @dp.message(AddMovie.waiting_code)
    async def addmovie_code(message: Message, state: FSMContext):
        code = message.text.strip()
        if not code.isdigit():
            await message.answer("❌ Kod faqat raqamlardan iborat bo'lishi kerak. Qaytadan yuboring:")
            return
        await state.update_data(code=code)
        await message.answer("Endi kino haqida qisqacha tavsif yozing (janr, yil, va h.k.):")
        await state.set_state(AddMovie.waiting_desc)

    @dp.message(AddMovie.waiting_desc)
    async def addmovie_desc(message: Message, state: FSMContext):
        await state.update_data(desc=message.text.strip())
        await message.answer("Endi filmni (videoni) yuboring:")
        await state.set_state(AddMovie.waiting_video)

    @dp.message(AddMovie.waiting_video, F.video)
    async def addmovie_video(message: Message, state: FSMContext):
        state_data = await state.get_data()
        code = state_data.get("code")
        desc = state_data.get("desc", "")
        info["movies"][code] = {"file_id": message.video.file_id, "desc": desc}
        save_data()
        await message.answer(f"✅ Kod <b>{code}</b> bilan film saqlandi.")
        await state.clear()

    @dp.message(AddMovie.waiting_video)
    async def addmovie_wrong(message: Message):
        await message.answer("❌ Iltimos, video fayl yuboring (forward qilingan bo'lsa ham bo'ladi).")

    @dp.message(F.text)
    async def get_movie(message: Message):
        if not await check_active(message, info, admin_id):
            return
        if not await require_subscription(message, info, admin_id):
            return
        code = message.text.strip()
        info["stats"]["requests"] += 1
        save_data()
        movie = info["movies"].get(code)
        if movie:
            caption = f"🎬 Kod: {code}"
            if movie.get("desc"):
                caption += f"\n\n{movie['desc']}"
            await message.answer_video(movie["file_id"], caption=caption)
        else:
            await message.answer("❌ Bunday kodli film topilmadi.")


# ---------- Savdo bot ----------
def setup_shop_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]
    admin_id = info["admin_id"]
    info["stats"].setdefault("orders", 0)
    info["stats"].setdefault("revenue", 0)
    setup_subscription_handlers(dp, token, admin_id)

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
        return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    def main_menu_kb():
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🛍 Mahsulotlar"), KeyboardButton(text="🛒 Savatim")]],
            resize_keyboard=True,
        )

    async def send_cart(user_id: int, send_func):
        uid = str(user_id)
        cart = info["carts"].get(uid, {})
        if not cart:
            await send_func("🛒 Savatingiz bo'sh.")
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
        await send_func(text, reply_markup=buttons)

    @dp.message(Command("start"))
    async def sstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        if not await check_active(message, info, admin_id):
            return
        if uid == admin_id:
            await message.answer("🛒 <b>Savdo bot boshqaruvi</b>\n\nStatistika: /stats\nMajburiy obuna: /channels", reply_markup=admin_kb())
            return
        if not await require_subscription(message, info, admin_id):
            return
        if not info["products"]:
            await message.answer("Hozircha mahsulotlar yo'q.", reply_markup=main_menu_kb())
        else:
            kb = catalog_kb()
            await message.answer("🛍 Mahsulotlar:", reply_markup=kb)
            await message.answer("Pastdagi menyudan foydalaning 👇", reply_markup=main_menu_kb())

    @dp.message(F.text == "🛍 Mahsulotlar")
    async def show_catalog(message: Message):
        if not await check_active(message, info, admin_id):
            return
        if not await require_subscription(message, info, admin_id):
            return
        kb = catalog_kb()
        if not kb:
            await message.answer("Hozircha mahsulotlar yo'q.")
        else:
            await message.answer("🛍 Mahsulotlar:", reply_markup=kb)

    @dp.message(F.text == "🛒 Savatim")
    async def show_cart_menu(message: Message):
        await send_cart(message.from_user.id, message.answer)

    @dp.message(Command("stats"))
    async def shop_stats(message: Message):
        if message.from_user.id != admin_id:
            return
        await message.answer(
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Foydalanuvchilar: {len(info['users'])}\n"
            f"🧾 Buyurtmalar: {info['stats']['orders']}\n"
            f"💰 Jami tushum: {info['stats']['revenue']:,} so'm"
        )

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

        # Mavjud xaridorlarga yangilangan katalogni tabiiy ko'rinishda yuborish
        for uid in info["users"]:
            if uid == admin_id:
                continue
            try:
                kb = catalog_kb()
                if kb:
                    await message.bot.send_message(uid, "🛍 Mahsulotlar:", reply_markup=kb)
            except Exception:
                pass

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
        if not await check_active(callback, info, admin_id):
            return
        if not await require_subscription(callback, info, admin_id):
            return
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
        await send_cart(callback.from_user.id, callback.message.answer)
        await callback.answer()

    @dp.callback_query(F.data == "cart_clear")
    async def cart_clear_cb(callback: CallbackQuery):
        uid = str(callback.from_user.id)
        info["carts"][uid] = {}
        save_data()
        await callback.message.answer("🗑 Savat tozalandi.")
        await callback.answer()

    @dp.callback_query(F.data == "checkout")
    async def checkout_cb(callback: CallbackQuery, state: FSMContext):
        uid = str(callback.from_user.id)
        cart = info["carts"].get(uid, {})
        if not cart:
            await callback.answer("Savat bo'sh.", show_alert=True)
            return
        await callback.message.answer("📍 Yetkazib berish manzilingizni yozing:")
        await state.set_state(Checkout.waiting_address)
        await callback.answer()

    @dp.message(Checkout.waiting_address)
    async def checkout_address(message: Message, state: FSMContext):
        await state.update_data(address=message.text.strip())
        await message.answer("📞 Telefon raqamingizni yuboring:")
        await state.set_state(Checkout.waiting_phone)

    @dp.message(Checkout.waiting_phone)
    async def checkout_phone(message: Message, state: FSMContext):
        phone = message.text.strip()
        state_data = await state.get_data()
        address = state_data.get("address", "-")

        uid = str(message.from_user.id)
        cart = info["carts"].get(uid, {})
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

        username = message.from_user.username or message.from_user.id
        order_text = (
            f"🛒 <b>Yangi buyurtma!</b>\n"
            f"Xaridor: @{username}\n"
            f"📍 Manzil: {address}\n"
            f"📞 Telefon: {phone}\n\n"
            + "\n".join(lines)
            + f"\n\n💰 Jami: {total:,} so'm"
        )
        await message.bot.send_message(admin_id, order_text)

        info["carts"][uid] = {}
        info["stats"]["orders"] += 1
        info["stats"]["revenue"] += total
        save_data()

        await message.answer("✅ Buyurtmangiz qabul qilindi! Tez orada siz bilan bog'lanishadi.")
        await state.clear()


# ---------- AI-yordamchi bot ----------
def setup_ai_bot(dp: Dispatcher, token: str):
    info = data["bots"][token]
    admin_id = info["admin_id"]
    info["stats"].setdefault("questions", 0)
    setup_subscription_handlers(dp, token, admin_id)

    @dp.message(Command("start"))
    async def astart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        if not await check_active(message, info, admin_id):
            return
        if uid == admin_id:
            await message.answer("🤖 Salom! Statistika: /stats, Majburiy obuna: /channels.\nSavol yozsangiz ham javob beraman.")
        else:
            await message.answer("🤖 Salom! Menga istalgan savolni yozing, sun'iy intellekt sifatida javob beraman.")

    @dp.message(Command("stats"))
    async def ai_stats(message: Message):
        if message.from_user.id != admin_id:
            return
        await message.answer(
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Foydalanuvchilar: {len(info['users'])}\n"
            f"❓ Savollar soni: {info['stats']['questions']}"
        )

    @dp.message(F.text)
    async def ai_chat(message: Message):
        if not await check_active(message, info, admin_id):
            return
        if not await require_subscription(message, info, admin_id):
            return
        info["stats"]["questions"] += 1
        save_data()
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
    info["stats"].setdefault("posts_sent", 0)
    setup_subscription_handlers(dp, token, admin_id)

    def admin_kb():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="newpost")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="pstats")],
        ])

    @dp.message(Command("start"))
    async def pstart(message: Message):
        uid = message.from_user.id
        if uid not in info["users"]:
            info["users"].append(uid)
            save_data()
        if not await check_active(message, info, admin_id):
            return
        if uid == admin_id:
            await message.answer("📢 <b>E'lon bot boshqaruvi</b>\n\nMajburiy obuna: /channels", reply_markup=admin_kb())
        else:
            await message.answer("📢 Yangiliklarga obuna bo'ldingiz!")

    @dp.message(Command("stats"))
    @dp.callback_query(F.data == "pstats")
    async def post_stats(event):
        if event.from_user.id != admin_id:
            return
        text = (
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Obunachilar: {len(info['users'])}\n"
            f"📤 Yuborilgan e'lonlar: {info['stats']['posts_sent']}"
        )
        if isinstance(event, CallbackQuery):
            await event.message.answer(text)
            await event.answer()
        else:
            await event.answer(text)

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
        info["stats"]["posts_sent"] += 1
        save_data()
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
        info.setdefault("stats", {})
        await start_child_bot(token, info["type"])
    await main_dp.start_polling(main_bot)


if __name__ == "__main__":
    asyncio.run(main())
