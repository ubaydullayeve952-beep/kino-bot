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

BOT_TOKEN = os.getenv("8606463536:AAFo9zlioN9CjWWmDkMa0Pf-voJC_EtLk1M")
MONGO_URI = os.getenv("ravshan0202@cluster0.8ncigsp.mongodb.net")
ADMIN_IDS = list(map(int, os.getenv("8965276284", "0").split(",")))

client = AsyncIOMotorClient(MONGO_URI)
db = client["kinobot"]
users_col = db["users"]
movies_col = db["movies"]
channels_col = db["channels"]
admins_col = db["admins"]

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logging.basicConfig(level=logging.INFO)

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
            "blocked": False,
            "joined": datetime.now(),
            "history": [],
            "favorites": []
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
        f"🎬 <b>Kino Botga xush kelibsiz!</b>\n\nSalom, <b>{message.from_user.full_name}</b>!\n\nKino kodini yuboring:",
        reply_markup=main_menu(adm)
    )

@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub_cb(call: types.CallbackQuery):
    if not await check_sub(call.from_user.id):
        await call.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    adm = await is_admin(call.from_user.id)
    await call.message.edit_text("✅ Obuna tasdiqlandi!", reply_markup=main_menu(adm))

async def send_movie(message, code):
    user = await get_user(message.from_user.id)
    movie = await movies_col.find_one({"code": code.upper()})
    if not movie:
        await message.answer("❌ Bunday kodli kino topilmadi!")
        return
    if movie.get("status") == "vip" and not (user.get("vip") or user.get("premium")):
        await message.answer("💎 Bu kino faqat VIP uchun!")
        return
    if movie.get("status") == "premium" and not user.get("premium"):
        await message.answer("👑 Bu kino faqat Premium uchun!")
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

@dp.callback_query_handler(lambda c: c.data == "profile")
async def profile(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    vip = "💎 VIP" if user.get("vip") else "❌"
    prem = "👑 Premium" if user.get("premium") else "❌"
    hist = len(user.get("history", []))
    favs = len(user.get("favorites", []))
    await call.message.edit_text(
        f"👤 <b>Profil</b>\n\n🆔 ID: <code>{call.from_user.id}</code>\n"
        f"📛 Ism: {call.from_user.full_name}\n💎 VIP: {vip}\n"
        f"👑 Premium: {prem}\n📋 Tarix: {hist} ta\n⭐ Sevimlilar: {favs} ta",
        reply_markup=back_btn()
    )

@dp.callback_query_handler(lambda c: c.data == "history")
async def history_cb(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    hist = user.get("history", [])
    if not hist:
        await call.answer("📋 Tarix bo'sh!", show_alert=True)
        return
    text = "📋 <b>Ko'rilgan kinolar:</b>\n\n"
    for code in hist[-15:]:
        text += f"🎬 <code>{code}</code>\n"
    await call.message.edit_text(text, reply_markup=back_btn())

@dp.callback_query_handler(lambda c: c.data == "favorites")
async def favorites_cb(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    favs = user.get("favorites", [])
    if not favs:
        await call.answer("⭐ Sevimlilar bo'sh!", show_alert=True)
        return
    text = "⭐ <b>Sevimli kinolar:</b>\n\n"
    for code in favs:
        text += f"🎬 <code>{code}</code>\n"
    await call.message.edit_text(text, reply_markup=back_btn())

@dp.callback_query_handler(lambda c: c.data == "vip_movies")
async def vip_movies(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    if not (user.get("vip") or user.get("premium")):
        await call.answer("💎 Faqat VIP uchun!", show_alert=True)
        return
    movies = await movies_col.find({"status": "vip"}).to_list(None)
    if not movies:
        await call.answer("Hozircha VIP kinolar yo'q", show_alert=True)
        return
    text = "💎 <b>VIP Kinolar:</b>\n\n"
    for m in movies:
        text += f"🎬 {m.get('title','?')} — <code>{m['code']}</code>\n"
    await call.message.edit_text(text, reply_markup=back_btn())

@dp.callback_query_handler(lambda c: c.data == "premium_movies")
async def premium_movies(call: types.CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user.get("premium"):
        await call.answer("👑 Faqat Premium uchun!", show_alert=True)
        return
    movies = await movies_col.find({"status": "premium"}).to_list(None)
    if not movies:
        await call.answer("Hozircha Premium kinolar yo'q", show_alert=True)
        return
    text = "👑 <b>Premium Kinolar:</b>\n\n"
    for m in movies:
        text += f"🎬 {m.get('title','?')} — <code>{m['code']}</code>\n"
    await call.message.edit_text(text, reply_markup=back_btn())

@dp.callback_query_handler(lambda c: c.data == "help")
async def help_cb(call: types.CallbackQuery):
    await call.message.edit_text(
        "ℹ️ <b>Yordam</b>\n\nKino olish uchun kino kodini yuboring.\n"
        "💎 VIP va 👑 Premium uchun adminga murojaat qiling.",
        reply_markup=back_btn()
    )

@dp.callback_query_handler(lambda c: c.data == "get_movie")
async def get_movie_cb(call: types.CallbackQuery):
    await call.message.edit_text("🎬 Kino kodini yuboring!\n\nMasalan: <code>KINO001</code>", reply_markup=back_btn())

@dp.callback_query_handler(lambda c: c.data == "back_main")
async def back_main(call: types.CallbackQuery):
    adm = await is_admin(call.from_user.id)
    await call.message.edit_text("🎬 Asosiy menyu:", reply_markup=main_menu(adm))

@dp.callback_query_handler(lambda c: c.data == "admin_panel")
async def admin_panel(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("⚙️ <b>Admin Panel</b>", reply_markup=admin_menu())

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    total = await users_col.count_documents({})
    vip = await users_col.count_documents({"vip": True})
    prem = await users_col.count_documents({"premium": True})
    blk = await users_col.count_documents({"blocked": True})
    mv = await movies_col.count_documents({})
    ch = await channels_col.count_documents({})
    await call.message.edit_text(
        f"📊 <b>Statistika</b>\n\n👥 Jami: {total}\n💎 VIP: {vip}\n"
        f"👑 Premium: {prem}\n🚫 Bloklangan: {blk}\n🎬 Kinolar: {mv}\n📢 Kanallar: {ch}",
        reply_markup=back_btn("admin_panel")
    )

@dp.callback_query_handler(lambda c: c.data == "users_list")
async def users_list(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    total = await users_col.count_documents({})
    users = await users_col.find().sort("joined", -1).limit(10).to_list(None)
    text = f"👥 <b>Foydalanuvchilar</b> (jami: {total})\n\n"
    for u in users:
        s = "💎" if u.get("vip") else "👑" if u.get("premium") else "👤"
        text += f"{s} {u.get('full_name','?')} — <code>{u['user_id']}</code>\n"
    await call.message.edit_text(text, reply_markup=back_btn("admin_panel"))

@dp.callback_query_handler(lambda c: c.data == "add_movie")
async def add_movie(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("🎬 Kino kodini kiriting (masalan: KINO001):")
    await MovieAdd.code.set()

@dp.message_handler(state=MovieAdd.code)
async def movie_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    if await movies_col.find_one({"code": code}):
        await message.answer(f"❌ {code} allaqachon bor! Boshqa kod:")
        return
    await state.update_data(code=code)
    await message.answer(f"✅ Kod: <b>{code}</b>\n\nKino nomini kiriting:")
    await MovieAdd.title.set()

@dp.message_handler(state=MovieAdd.title)
async def movie_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🆓 Bepul", callback_data="ms_free"))
    kb.add(InlineKeyboardButton("💎 VIP", callback_data="ms_vip"))
    kb.add(InlineKeyboardButton("👑 Premium", callback_data="ms_premium"))
    await message.answer("Status tanlang:", reply_markup=kb)
    await MovieAdd.status.set()

@dp.callback_query_handler(lambda c: c.data.startswith("ms_"), state=MovieAdd.status)
async def movie_status(call: types.CallbackQuery, state: FSMContext):
    status = call.data.replace("ms_", "")
    await state.update_data(status=status)
    await call.message.edit_text("Endi kino faylini yuboring (video/rasm):")
    await MovieAdd.file.set()

@dp.message_handler(state=MovieAdd.file, content_types=types.ContentTypes.ANY)
async def movie_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await movies_col.insert_one({
        "code": data["code"],
        "title": data["title"],
        "status": data["status"],
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "added": datetime.now()
    })
    await state.finish()
    await message.answer(
        f"✅ Kino qo'shildi!\nKod: <code>{data['code']}</code>",
        reply_markup=back_btn("admin_panel")
    )

@dp.callback_query_handler(lambda c: c.data == "del_movie")
async def del_movie(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("🗑 O'chiriladigan kino kodini kiriting:")
    await DelMovie.code.set()

@dp.message_handler(state=DelMovie.code)
async def del_movie_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    result = await movies_col.delete_one({"code": code})
    await state.finish()
    if result.deleted_count:
        await message.answer(f"✅ {code} o'chirildi!", reply_markup=back_btn("admin_panel"))
    else:
        await message.answer(f"❌ {code} topilmadi!", reply_markup=back_btn("admin_panel"))

@dp.callback_query_handler(lambda c: c.data == "add_channel")
async def add_channel(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("📢 Kanal ID sini kiriting (masalan: -1001234567890)\nBotni kanalga admin qiling!")
    await ChannelAdd.channel_id.set()

@dp.message_handler(state=ChannelAdd.channel_id)
async def save_channel(message: types.Message, state: FSMContext):
    await state.finish()
    try:
        ch_id = int(message.text.strip())
        chat = await bot.get_chat(ch_id)
        link = await bot.export_chat_invite_link(ch_id)
        await channels_col.insert_one({"channel_id": ch_id, "title": chat.title, "invite_link": link})
        await message.answer(f"✅ Kanal qo'shildi: {chat.title}", reply_markup=back_btn("admin_panel"))
    except Exception as e:
        await message.answer(f"❌ Xato: {e}", reply_markup=back_btn("admin_panel"))

@dp.callback_query_handler(lambda c: c.data == "del_channel")
async def del_channel(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    channels = await channels_col.find().to_list(None)
    if not channels:
        await call.answer("Kanallar yo'q!", show_alert=True)
        return
    kb = InlineKeyboardMarkup()
    for ch in channels:
        kb.add(InlineKeyboardButton(f"🗑 {ch['title']}", callback_data=f"dch_{ch['channel_id']}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel"))
    await call.message.edit_text("O'chiriladigan kanalni tanlang:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("dch_"))
async def remove_channel(call: types.CallbackQuery):
    ch_id = int(call.data.split("_")[1])
    await channels_col.delete_one({"channel_id": ch_id})
    await call.answer("✅ O'chirildi!", show_alert=True)
    await del_channel(call)

@dp.callback_query_handler(lambda c: c.data == "add_admin")
async def add_admin(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("👮 Yangi admin ID sini kiriting:")
    await AdminAdd.user_id.set()

@dp.message_handler(state=AdminAdd.user_id)
async def save_admin(message: types.Message, state: FSMContext):
    await state.finish()
    try:
        uid = int(message.text.strip())
        await admins_col.update_one({"user_id": uid}, {"$set": {"user_id": uid}}, upsert=True)
        await message.answer(f"✅ Admin qo'shildi: {uid}", reply_markup=back_btn("admin_panel"))
    except:
        await message.answer("❌ Xato ID!", reply_markup=back_btn("admin_panel"))

@dp.callback_query_handler(lambda c: c.data == "del_admin")
async def del_admin(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    admins = await admins_col.find().to_list(None)
    if not admins:
        await call.answer("Adminlar yo'q!", show_alert=True)
        return
    kb = InlineKeyboardMarkup()
    for a in admins:
        kb.add(InlineKeyboardButton(f"❌ {a['user_id']}", callback_data=f"dadm_{a['user_id']}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel"))
    await call.message.edit_text("O'chiriladigan adminni tanlang:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("dadm_"))
async def remove_admin(call: types.CallbackQuery):
    uid = int(call.data.split("_")[1])
    await admins_col.delete_one({"user_id": uid})
    await call.answer("✅ Admin o'chirildi!", show_alert=True)
    await del_admin(call)

@dp.callback_query_handler(lambda c: c.data == "give_vip")
async def give_vip(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("💎 VIP beriladigan foydalanuvchi ID sini kiriting:")
    await VipGive.user_id.set()

@dp.message_handler(state=VipGive.user_id)
async def vip_user(message: types.Message, state: FSMContext):
    await state.update_data(user_id=int(message.text.strip()))
    await message.answer("Necha kun VIP? (raqam):")
    await VipGive.days.set()

@dp.message_handler(state=VipGive.days)
async def vip_days(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.finish()
    days = int(message.text.strip())
    until = datetime.now() + timedelta(days=days)
    await users_col.update_one({"user_id": data["user_id"]}, {"$set": {"vip": True, "vip_until": until}})
    try:
        await bot.send_message(data["user_id"], f"🎉 Sizga {days} kunlik 💎 VIP berildi!")
    except:
        pass
    await message.answer(f"✅ {data['user_id']} ga {days} kun VIP berildi!", reply_markup=back_btn("admin_panel"))

@dp.callback_query_handler(lambda c: c.data == "give_premium")
async def give_premium(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("👑 Premium beriladigan foydalanuvchi ID sini kiriting:")
    await PremiumGive.user_id.set()

@dp.message_handler(state=PremiumGive.user_id)
async def premium_user(message: types.Message, state: FSMContext):
    await state.update_data(user_id=int(message.text.strip()))
    await message.answer("Necha kun Premium? (raqam):")
    await PremiumGive.days.set()

@dp.message_handler(state=PremiumGive.days)
async def premium_days(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.finish()
    days = int(message.text.strip())
    until = datetime.now() + timedelta(days=days)
    await users_col.update_one({"user_id": data["user_id"]}, {"$set": {"premium": True, "premium_until": until}})
    try:
        await bot.send_message(data["user_id"], f"🎉 Sizga {days} kunlik 👑 Premium berildi!")
    except:
        pass
    await message.answer(f"✅ {data['user_id']} ga {days} kun Premium berildi!", reply_markup=back_btn("admin_panel"))

@dp.callback_query_handler(lambda c: c.data == "block_user")
async def block_user(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("🚫 Bloklanadigan foydalanuvchi ID sini kiriting:")
    await BlockUser.user_id.set()

@dp.message_handler(state=BlockUser.user_id)
async def save_block(message: types.Message, state: FSMContext):
    await state.finish()
    try:
        uid = int(message.text.strip())
        await users_col.update_one({"user_id": uid}, {"$set": {"blocked": True}})
        await message.answer(f"✅ {uid} bloklandi!", reply_markup=back_btn("admin_panel"))
    except:
        await message.answer("❌ Xato!", reply_markup=back_btn("admin_panel"))

@dp.callback_query_handler(lambda c: c.data == "unblock_user")
async def unblock_user(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("✅ Blokdan chiqariladigan foydalanuvchi ID sini kiriting:")
    await UnblockUser.user_id.set()

@dp.message_handler(state=UnblockUser.user_id)
async def save_unblock(message: types.Message, state: FSMContext):
    await state.finish()
    try:
        uid = int(message.text.strip())
        await users_col.update_one({"user_id": uid}, {"$set": {"blocked": False}})
        await message.answer(f"✅ {uid} blokdan chiqarildi!", reply_markup=back_btn("admin_panel"))
    except:
        await message.answer("❌ Xato!", reply_markup=back_btn("admin_panel"))

@dp.callback_query_handler(lambda c: c.data == "broadcast")
async def broadcast(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("📣 Yuboriladigan xabarni kiriting:")
    await BroadcastState.message.set()

@dp.message_handler(state=BroadcastState.message, content_types=types.ContentTypes.ANY)
async def send_broadcast(message: types.Message, state: FSMContext):
    await state.finish()
    users = await users_col.find({"blocked": False}).to_list(None)
    sent, failed = 0, 0
    for u in users:
        try:
            await message.copy_to(u["user_id"])
            sent += 1
        except:
            failed += 1
    await message.answer(f"📣 Yuborildi!\n✅ {sent} ta\n❌ {failed} ta xato")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
