import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ChatMemberUpdated
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timedelta

# ======= SOZLAMALAR =======
BOT_TOKEN = os.getenv("8606463536:AAHbXjjAgrlaw6BrcWg96fUmy9dXUnrDK3c")
MONGO_URI = os.getenv("mongodb+srv://admin:ravshan0202@cluster0.8ncigsp.mongodb.net/kinodb?retryWrites=true&w=majority")
ADMIN_IDS = list(map(int, os.getenv("8965276284", "").split(",")))

# ======= DATABASE =======
client = AsyncIOMotorClient(MONGO_URI)
db = client["kinobot"]
users_col = db["users"]
movies_col = db["movies"]
channels_col = db["channels"]
admins_col = db["admins"]

# ======= BOT =======
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

logging.basicConfig(level=logging.INFO)

# ======= STATES =======
class AddMovie(StatesGroup):
    code = State()
    content = State()
    status = State()

class Broadcast(StatesGroup):
    message = State()

class AddChannel(StatesGroup):
    channel = State()

class AddAdmin(StatesGroup):
    user_id = State()

class GiveVip(StatesGroup):
    user_id = State()
    days = State()

# ======= YORDAMCHI FUNKSIYALAR =======

async def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    admin = await admins_col.find_one({"user_id": user_id})
    return admin is not None

async def get_user(user_id: int):
    return await users_col.find_one({"user_id": user_id})

async def add_user(user_id: int, username: str, full_name: str):
    existing = await users_col.find_one({"user_id": user_id})
    if not existing:
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
            "favorites": [],
            "history": []
        })

async def check_subscriptions(user_id: int) -> bool:
    channels = await channels_col.find().to_list(None)
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["channel_id"], user_id)
            if member.status in ["left", "kicked", "banned"]:
                return False
        except:
            pass
    return True

async def get_subscribe_keyboard():
    channels = await channels_col.find().to_list(None)
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch['title']}",
            url=ch["invite_link"]
        )])
    buttons.append([InlineKeyboardButton(
        text="✅ Tekshirish", callback_data="check_sub"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def main_menu(is_adm=False):
    buttons = [
        [InlineKeyboardButton(text="🎬 Kino olish", callback_data="get_movie")],
        [InlineKeyboardButton(text="⭐ Sevimlilar", callback_data="favorites"),
         InlineKeyboardButton(text="📋 Tarix", callback_data="history")],
        [InlineKeyboardButton(text="👤 Profilim", callback_data="profile")],
        [InlineKeyboardButton(text="💎 VIP kinolar", callback_data="vip_movies"),
         InlineKeyboardButton(text="👑 Premium", callback_data="premium_movies")],
        [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help")]
    ]
    if is_adm:
        buttons.append([InlineKeyboardButton(text="⚙️ Admin panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Kino qo'shish", callback_data="add_movie"),
         InlineKeyboardButton(text="🗑 Kino o'chirish", callback_data="del_movie")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="users_list"),
         InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton(text="💎 VIP berish", callback_data="give_vip"),
         InlineKeyboardButton(text="👑 Premium berish", callback_data="give_premium")],
        [InlineKeyboardButton(text="📢 Kanal qo'shish", callback_data="add_channel"),
         InlineKeyboardButton(text="📵 Kanal o'chirish", callback_data="del_channel")],
        [InlineKeyboardButton(text="👮 Admin qo'shish", callback_data="add_admin"),
         InlineKeyboardButton(text="❌ Admin o'chirish", callback_data="del_admin")],
        [InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="broadcast"),
         InlineKeyboardButton(text="🚫 Bloklash", callback_data="block_user")],
        [InlineKeyboardButton(text="✅ Blokdan chiqarish", callback_data="unblock_user")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")]
    ])

# ======= START =======
@router.message(CommandStart())
async def start(message: Message):
    await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    user = await get_user(message.from_user.id)
    if user and user.get("blocked"):
        await message.answer("🚫 Siz botdan bloklangansiz.")
        return
    subscribed = await check_subscriptions(message.from_user.id)
    if not subscribed:
        kb = await get_subscribe_keyboard()
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=kb
        )
        return
    adm = await is_admin(message.from_user.id)
    args = message.text.split()
    if len(args) > 1:
        code = args[1]
        await send_movie_by_code(message, code)
        return
    await message.answer(
        f"🎬 <b>Kino Botga xush kelibsiz!</b>\n\n"
        f"👤 Salom, <b>{message.from_user.full_name}</b>!\n\n"
        f"Kino kodini yuboring yoki menyu tugmalaridan foydalaning:",
        reply_markup=main_menu(adm),
        parse_mode="HTML"
    )

# ======= OBUNA TEKSHIRISH =======
@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    subscribed = await check_subscriptions(call.from_user.id)
    if not subscribed:
        await call.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    adm = await is_admin(call.from_user.id)
    await call.message.edit_text(
        "✅ Obuna tasdiqlandi! Botdan foydalanishingiz mumkin.",
        reply_markup=main_menu(adm)
    )

# ======= KINO OLISH =======
async def send_movie_by_code(message: Message, code: str):
    user = await get_user(message.from_user.id)
    movie = await movies_col.find_one({"code": code.upper()})
    if not movie:
        await message.answer("❌ Bunday kodli kino topilmadi!")
        return
    if movie.get("status") == "vip" and not (user.get("vip") or user.get("premium")):
        await message.answer("💎 Bu kino faqat VIP foydalanuvchilar uchun!\n\nVIP olish uchun adminга murojaat qiling.")
        return
    if movie.get("status") == "premium" and not user.get("premium"):
        await message.answer("👑 Bu kino faqat Premium foydalanuvchilar uchun!\n\nPremium olish uchun adminga murojaat qiling.")
        return
    await users_col.update_one(
        {"user_id": message.from_user.id},
        {"$addToSet": {"history": code.upper()}}
    )
    await message.answer_copy_from(
        from_chat_id=movie["chat_id"],
        message_id=movie["message_id"]
    )

@router.message(F.text & ~F.text.startswith("/"))
async def handle_code(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return
    user = await get_user(message.from_user.id)
    if not user:
        await start(message)
        return
    if user.get("blocked"):
        await message.answer("🚫 Siz botdan bloklangansiz.")
        return
    subscribed = await check_subscriptions(message.from_user.id)
    if not subscribed:
        kb = await get_subscribe_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb)
        return
    code = message.text.strip().upper()
    await send_movie_by_code(message, code)

# ======= PROFIL =======
@router.callback_query(F.data == "profile")
async def profile(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    vip_status = "💎 VIP" if user.get("vip") else "❌"
    premium_status = "👑 Premium" if user.get("premium") else "❌"
    vip_until = user.get("vip_until")
    prem_until = user.get("premium_until")
    text = (
        f"👤 <b>Profilingiz</b>\n\n"
        f"🆔 ID: <code>{call.from_user.id}</code>\n"
        f"📛 Ism: {call.from_user.full_name}\n"
        f"💎 VIP: {vip_status}"
    )
    if vip_until:
        text += f" (muddati: {vip_until.strftime('%d.%m.%Y')})"
    text += f"\n👑 Premium: {premium_status}"
    if prem_until:
        text += f" (muddati: {prem_until.strftime('%d.%m.%Y')})"
    fav_count = len(user.get("favorites", []))
    hist_count = len(user.get("history", []))
    text += f"\n⭐ Sevimlilar: {fav_count} ta\n📋 Ko'rilgan: {hist_count} ta"
    await call.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")
        ]]))

# ======= SEVIMLILAR =======
@router.callback_query(F.data == "favorites")
async def favorites(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    favs = user.get("favorites", [])
    if not favs:
        await call.answer("⭐ Sevimlilar ro'yxati bo'sh!", show_alert=True)
        return
    text = "⭐ <b>Sevimli kinolaringiz:</b>\n\n"
    for code in favs:
        movie = await movies_col.find_one({"code": code})
        if movie:
            text += f"🎬 {movie.get('title', code)} - Kod: <code>{code}</code>\n"
    await call.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")
        ]]))

# ======= TARIX =======
@router.callback_query(F.data == "history")
async def history(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    hist = user.get("history", [])
    if not hist:
        await call.answer("📋 Tarix bo'sh!", show_alert=True)
        return
    text = "📋 <b>Ko'rilgan kinolar:</b>\n\n"
    for code in hist[-20:]:
        text += f"🎬 Kod: <code>{code}</code>\n"
    await call.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")
        ]]))

# ======= YORDAM =======
@router.callback_query(F.data == "help")
async def help_cmd(call: CallbackQuery):
    await call.message.edit_text(
        "ℹ️ <b>Yordam</b>\n\n"
        "🎬 Kino olish uchun kino kodini yuboring\n"
        "💎 VIP - maxsus kinolarga kirish\n"
        "👑 Premium - barcha kinolarga kirish\n\n"
        "📞 Admin: @admin_username",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")
        ]])
    )

# ======= ORQAGA =======
@router.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery):
    adm = await is_admin(call.from_user.id)
    await call.message.edit_text(
        "🎬 Asosiy menyu:",
        reply_markup=main_menu(adm)
    )

# ======= VIP KINOLAR =======
@router.callback_query(F.data == "vip_movies")
async def vip_movies(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not (user.get("vip") or user.get("premium")):
        await call.answer("💎 Faqat VIP foydalanuvchilar uchun!", show_alert=True)
        return
    movies = await movies_col.find({"status": "vip"}).to_list(None)
    if not movies:
        await call.answer("Hozircha VIP kinolar yo'q", show_alert=True)
        return
    text = "💎 <b>VIP Kinolar:</b>\n\n"
    for m in movies:
        text += f"🎬 {m.get('title','Nomsiz')} - Kod: <code>{m['code']}</code>\n"
    await call.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")
        ]]))

# ======= PREMIUM KINOLAR =======
@router.callback_query(F.data == "premium_movies")
async def premium_movies(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user.get("premium"):
        await call.answer("👑 Faqat Premium foydalanuvchilar uchun!", show_alert=True)
        return
    movies = await movies_col.find({"status": "premium"}).to_list(None)
    if not movies:
        await call.answer("Hozircha Premium kinolar yo'q", show_alert=True)
        return
    text = "👑 <b>Premium Kinolar:</b>\n\n"
    for m in movies:
        text += f"🎬 {m.get('title','Nomsiz')} - Kod: <code>{m['code']}</code>\n"
    await call.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")
        ]]))

# ======= ADMIN PANEL =======
@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("⚙️ <b>Admin Panel</b>", parse_mode="HTML",
        reply_markup=admin_keyboard())

# ======= STATISTIKA =======
@router.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    total = await users_col.count_documents({})
    vip = await users_col.count_documents({"vip": True})
    premium = await users_col.count_documents({"premium": True})
    blocked = await users_col.count_documents({"blocked": True})
    movies = await movies_col.count_documents({})
    channels = await channels_col.count_documents({})
    await call.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: {total}\n"
        f"💎 VIP: {vip}\n"
        f"👑 Premium: {premium}\n"
        f"🚫 Bloklangan: {blocked}\n"
        f"🎬 Kinolar soni: {movies}\n"
        f"📢 Kanallar: {channels}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_panel")
        ]])
    )

# ======= KINO QO'SHISH =======
@router.callback_query(F.data == "add_movie")
async def add_movie_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text(
        "🎬 Kino kodini kiriting (masalan: KINO001):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_panel")
        ]])
    )
    await state.set_state(AddMovie.code)

@router.message(AddMovie.code)
async def add_movie_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    existing = await movies_col.find_one({"code": code})
    if existing:
        await message.answer(f"❌ {code} kodi allaqachon mavjud! Boshqa kod kiriting:")
        return
    await state.update_data(code=code)
    await message.answer(
        f"✅ Kod: <b>{code}</b>\n\nEndi kino nomini kiriting:",
        parse_mode="HTML"
    )
    await state.set_state(AddMovie.content)

@router.message(AddMovie.content)
async def add_movie_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer(
        "Kino statusini tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🆓 Bepul", callback_data="status_free")],
            [InlineKeyboardButton(text="💎 VIP", callback_data="status_vip")],
            [InlineKeyboardButton(text="👑 Premium", callback_data="status_premium")]
        ])
    )
    await state.set_state(AddMovie.status)

@router.callback_query(AddMovie.status)
async def add_movie_status(call: CallbackQuery, state: FSMContext):
    status_map = {"status_free": "free", "status_vip": "vip", "status_premium": "premium"}
    status = status_map.get(call.data, "free")
    data = await state.get_data()
    await state.update_data(status=status)
    await call.message.edit_text(
        f"✅ Kod: <b>{data['code']}</b>\n"
        f"📛 Nom: <b>{data['title']}</b>\n"
        f"🏷 Status: <b>{status}</b>\n\n"
        f"Endi kino faylini (video/foto/xabar) yuboring:",
        parse_mode="HTML"
    )

@router.message(AddMovie.status)
async def add_movie_file(message: Message, state: FSMContext):
    data = await state.get_data()
    await movies_col.insert_one({
        "code": data["code"],
        "title": data["title"],
        "status": data.get("status", "free"),
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "added": datetime.now()
    })
    await message.answer(
        f"✅ Kino muvaffaqiyatli qo'shildi!\n"
        f"📋 Kod: <code>{data['code']}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚙️ Admin panel", callback_data="admin_panel")
        ]])
    )
    await state.clear()

# ======= KINO O'CHIRISH =======
@router.callback_query(F.data == "del_movie")
async def del_movie_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("🗑 O'chiriladigan kino kodini kiriting:")
    await state.set_state(AddMovie.code)

# ======= BROADCAST =======
@router.callback_query(F.data == "broadcast")
async def broadcast_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("📣 Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:")
    await state.set_state(Broadcast.message)

@router.message(Broadcast.message)
async def broadcast_send(message: Message, state: FSMContext):
    await state.clear()
    users = await users_col.find({"blocked": False}).to_list(None)
    sent = 0
    failed = 0
    for user in users:
        try:
            await message.copy_to(user["user_id"])
            sent += 1
        except:
            failed += 1
    await message.answer(f"📣 Xabar yuborildi!\n✅ Muvaffaqiyatli: {sent}\n❌ Xato: {failed}")

# ======= KANAL QO'SHISH =======
@router.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text(
        "📢 Kanal ID sini kiriting (masalan: -1001234567890)\n"
        "Botni kanalga admin qiling va ID ni yuboring:"
    )
    await state.set_state(AddChannel.channel)

@router.message(AddChannel.channel)
async def add_channel_save(message: Message, state: FSMContext):
    await state.clear()
    try:
        channel_id = int(message.text.strip())
        chat = await bot.get_chat(channel_id)
        invite = await bot.export_chat_invite_link(channel_id)
        await channels_col.insert_one({
            "channel_id": channel_id,
            "title": chat.title,
            "invite_link": invite
        })
        await message.answer(f"✅ Kanal qo'shildi: {chat.title}")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

# ======= KANAL O'CHIRISH =======
@router.callback_query(F.data == "del_channel")
async def del_channel(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    channels = await channels_col.find().to_list(None)
    if not channels:
        await call.answer("Kanallar yo'q!", show_alert=True)
        return
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {ch['title']}",
            callback_data=f"rmch_{ch['channel_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_panel")])
    await call.message.edit_text("O'chiriladigan kanalni tanlang:", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("rmch_"))
async def remove_channel(call: CallbackQuery):
    channel_id = int(call.data.split("_")[1])
    await channels_col.delete_one({"channel_id": channel_id})
    await call.answer("✅ Kanal o'chirildi!", show_alert=True)
    await del_channel(call)

# ======= ADMIN QO'SHISH =======
@router.callback_query(F.data == "add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("👮 Yangi admin user ID sini kiriting:")
    await state.set_state(AddAdmin.user_id)

@router.message(AddAdmin.user_id)
async def add_admin_save(message: Message, state: FSMContext):
    await state.clear()
    try:
        user_id = int(message.text.strip())
        await admins_col.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "added_by": message.from_user.id, "added": datetime.now()}},
            upsert=True
        )
        await message.answer(f"✅ Admin qo'shildi! ID: {user_id}")
    except:
        await message.answer("❌ Xato ID!")

# ======= ADMIN O'CHIRISH =======
@router.callback_query(F.data == "del_admin")
async def del_admin_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    admins = await admins_col.find().to_list(None)
    if not admins:
        await call.answer("Adminlar yo'q!", show_alert=True)
        return
    buttons = []
    for adm in admins:
        buttons.append([InlineKeyboardButton(
            text=f"❌ {adm['user_id']}",
            callback_data=f"rmadm_{adm['user_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_panel")])
    await call.message.edit_text("O'chiriladigan adminni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("rmadm_"))
async def remove_admin(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    await admins_col.delete_one({"user_id": user_id})
    await call.answer("✅ Admin o'chirildi!", show_alert=True)
    await del_admin_start(call, None)

# ======= VIP BERISH =======
@router.callback_query(F.data == "give_vip")
async def give_vip_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("💎 VIP beriladigan foydalanuvchi ID sini kiriting:")
    await state.set_state(GiveVip.user_id)

@router.message(GiveVip.user_id)
async def give_vip_days(message: Message, state: FSMContext):
    await state.update_data(user_id=int(message.text.strip()))
    await message.answer("Necha kun VIP berilsin? (raqam kiriting):")
    await state.set_state(GiveVip.days)

@router.message(GiveVip.days)
async def give_vip_save(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    days = int(message.text.strip())
    until = datetime.now() + timedelta(days=days)
    await users_col.update_one(
        {"user_id": data["user_id"]},
        {"$set": {"vip": True, "vip_until": until}}
    )
    try:
        await bot.send_message(data["user_id"],
            f"🎉 Sizga {days} kunlik <b>💎 VIP</b> status berildi!\n"
            f"Muddati: {until.strftime('%d.%m.%Y')}", parse_mode="HTML")
    except:
        pass
    await message.answer(f"✅ {data['user_id']} ga {days} kunlik VIP berildi!")

# ======= PREMIUM BERISH =======
@router.callback_query(F.data == "give_premium")
async def give_premium_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("👑 Premium beriladigan foydalanuvchi ID sini kiriting:")
    await state.set_state(GiveVip.user_id)

# ======= BLOKLASH =======
@router.callback_query(F.data == "block_user")
async def block_user_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("🚫 Bloklanadigan foydalanuvchi ID sini kiriting:")
    await state.set_state(AddAdmin.user_id)

# ======= FOYDALANUVCHILAR RO'YXATI =======
@router.callback_query(F.data == "users_list")
async def users_list(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    total = await users_col.count_documents({})
    users = await users_col.find().sort("joined", -1).limit(10).to_list(None)
    text = f"👥 <b>Foydalanuvchilar</b> (jami: {total})\n\nSo'nggi 10 ta:\n\n"
    for u in users:
        status = "💎" if u.get("vip") else "👑" if u.get("premium") else "👤"
        text += f"{status} {u.get('full_name','?')} - <code>{u['user_id']}</code>\n"
    await call.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_panel")
        ]]))

# ======= GET MOVIE CALLBACK =======
@router.callback_query(F.data == "get_movie")
async def get_movie_cb(call: CallbackQuery):
    await call.message.edit_text(
        "🎬 Kino kodini yuboring!\n\nMasalan: <code>KINO001</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")
        ]])
    )

# ======= ISHGA TUSHIRISH =======
async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
