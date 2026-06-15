import asyncio
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timedelta

# ======= SOZLAMALAR =======
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))

# ======= DATABASE =======
client = AsyncIOMotorClient(MONGO_URI)
db = client["kinobot"]
users_col = db["users"]
movies_col = db["movies"]
channels_col = db["channels"]
admins_col = db["admins"]

# ======= BOT =======
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logging.basicConfig(level=logging.INFO)

# ======= STATES =======
class MovieAdd(StatesGroup):
    code = State()
    title = State()
    status = State()
    file = State()

class BroadcastState(StatesGroup):
    message = State()

class ChannelAdd(StatesGroup):
    channel_id = State()

class AdminAdd(StatesGroup):
    user_id = State()

class AdminDel(StatesGroup):
    user_id = State()

class VipGive(StatesGroup):
    user_id = State()
    days = State()

class PremiumGive(StatesGroup):
    user_id = State()
    days = State()

class BlockUser(StatesGroup):
    user_id = State()

class UnblockUser(StatesGroup):
    user_id = State()

class DelMovie(StatesGroup):
    code = State()

# ======= YORDAMCHI =======
async def is_admin(user_id):
    if user_id in ADMIN_IDS:
        return True
    return await admins_col.find_one({"user_id": user_id}) is not None

async def get_user(user_id):
    return await users_col.find_one({"user_id": user_id})

async def add_user(user_id, username, full_name):
    if not await users_col.find_one({"user_id": user_id}):
        await users_col.insert_one({
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "vip": False,
            "premium": False,
            "vip_until": None,
            "premium_until": None,
            "blocked": False,
            "joined": datetime.now(),
            "history": []
        })

async def check_sub(user_id):
    channels = await channels_col.find().to_list(None)
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["channel_id"], user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            pass
    return True

async def sub_keyboard():
    channels = await channels_col.find().to_list(None)
    kb = InlineKeyboardMarkup()
    for ch in channels:
        kb.add(InlineKeyboardButton(f"📢 {ch['title']}", url=ch["invite_link"]))
    kb.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    return kb

def main_menu(adm=False):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎬 Kino olish", callback_data="get_movie"),
        InlineKeyboardButton("👤 Profilim", callback_data="profile")
    )
    kb.add(
        InlineKeyboardButton("⭐ Sevimlilar", callback_data="favorites"),
        InlineKeyboardButton("📋 Tarix", callback_data="history")
    )
    kb.add(
        InlineKeyboardButton("💎 VIP kinolar", callback_data="vip_movies"),
        InlineKeyboardButton("👑 Premium", callback_data="premium_movies")
    )
    kb.add(InlineKeyboardButton("ℹ️ Yordam", callback_data="help"))
    if adm:
        kb.add(InlineKeyboardButton("⚙️ Admin panel", callback_data="admin_panel"))
    return kb

def admin_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎬 Kino qo'shish", callback_data="add_movie"),
        InlineKeyboardButton("🗑 Kino o'chirish", callback_data="del_movie")
    )
    kb.add(
        InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="users_list"),
        InlineKeyboardButton("📊 Statistika", callback_data="stats")
    )
    kb.add(
        InlineKeyboardButton("💎 VIP berish", callback_data="give_vip"),
        InlineKeyboardButton("👑 Premium berish", callback_data="give_premium")
    )
    kb.add(
        InlineKeyboardButton("📢 Kanal qo'shish", callback_data="add_channel"),
        InlineKeyboardButton("📵 Kanal o'chirish", callback_data="del_channel")
    )
    kb.add(
        InlineKeyboardButton("👮 Admin qo'shish", callback_data="add_admin"),
        InlineKeyboardButton("❌ Admin o'chirish", callback_data="del_admin")
    )
    kb.add(
        InlineKeyboardButton("📣 Xabar yuborish", callback_data="broadcast"),
        InlineKeyboardButton("🚫 Bloklash", callback_data="block_user")
    )
    kb.add(InlineKeyboardButton("✅ Blokdan chiqarish", callback_data="unblock_user"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back_main"))
    return kb

def back_btn(cb="back_main"):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data=cb))
    return kb

# ======= START =======
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    user = await get_user(message.from_user.id)
    if user and user.get("blocked"):
        await message.answer("🚫 Siz botdan bloklangansiz.")
        return
    if not await check_sub(message.from_user.id):
        kb = await sub_keyboard()
        await message.answer("⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=kb)
        return
    args = message.get_args()
    if args:
        await send_movie(message, args)
        return
    adm = await is_admin(message.from_user.id)
    await message.answer(
        f"🎬 <b>Kino Botga xush kelibsiz!</b>\n\n"
        f"Salom, <b>{message.from_user.full_name}</b>!\n\n"
        f"Kino kodini yuboring yoki tugmalardan foydalaning:",
        reply_markup=main_menu(adm)
    )

# ======= OBUNA =======
@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub_cb(call: types.CallbackQuery):
    if not await check_sub(call.from_user.id):
        await call.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    adm = await is_admin(call.from_user.id)
    await call.message.edit_text("✅ Obuna tasdiqlandi!", reply_markup=main_menu(adm))

# ======= KINO YUBORISH =======
async def send_movie(message, code):
    user = await get_user(message.from_user.id)
    movie = await movies_col.find_one({"code": code.upper()})
    if not movie:
        await message.answer("❌ Bunday kodli kino topilmadi!")
        return
    if movie.get("status") == "vip" and not (user.get("vip") or user.get("premium")):
        await message.answer("💎 Bu kino faqat VIP uchun!\nAdmin: @admin_username")
        return
    if movie.get("status") == "premium" and not user.get("premium"):
        await message.answer("👑 Bu kino faqat Premium uchun!\nAdmin: @admin_username")
        return
    await users_col.update_one({"user_id": message.from_user.id}, {"$addToSet": {"history": code.upper()}})
    await bot.copy_message(message.chat.id, movie["chat_id"], movie["message_id"])

@dp.message_handler(lambda m: not m.text.startswith("/"))
async def handle_text(message: types.Message, state: FSMContext):
    if await state.get_state():
        return
    user = await get_user(message.from_user.id)
    if not user:
        await start(message)
        return
    if user.get("blocked"):
        await message.answer("🚫 Siz botdan bloklangansiz.")
        return
    if not await check_sub(message.from_user.id):
        kb = await sub_keyboard()
        await message.answer("⚠️ Avval obuna bo'ling:", reply_markup=kb)
        return
    await send_movie(message, message.text.strip())

# ======= PROFIL =======
@dp.callback_query_handler(lambda c: c.data == "profile")
async def profile(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    vip = "💎 VIP" if user.get("vip") else "❌"
    prem = "👑 Premium" if user.get("premium") else "❌"
    hist = len(user.get("history", []))
    await call.message.edit_text(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 ID: <code>{call.from_user.id}</code>\n"
        f"📛 Ism: {call.from_user.full_name}\n"
        f"💎 VIP: {vip}\n"
        f"👑 Premium: {prem}\n"
        f"📋 Ko'rilgan: {hist} ta",
        reply_markup=back_btn()
    )

# ======= TARIX =======
@dp.callback_query_handler(lambda c: c.data == "history")
async def history(call: types.CallbackQuery):
    user = await get_user(call
