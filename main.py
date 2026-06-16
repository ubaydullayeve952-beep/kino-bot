import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import os
from datetime import datetime

# === SOZLAMALAR ===
TOKEN = os.getenv("TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))

# === DATABASE ===
client = MongoClient(MONGO_URI)
db = client["kinobot"]
users = db["users"]
movies = db["movies"]
admins = db["admins"]
sponsors = db["sponsors"]

bot = telebot.TeleBot(TOKEN)

# === YORDAMCHI ===
def is_admin(uid):
    if uid in ADMIN_IDS:
        return True
    return admins.find_one({"uid": uid}) is not None

def add_user(uid, username, name):
    if not users.find_one({"uid": uid}):
        users.insert_one({
            "uid": uid,
            "username": username,
            "name": name,
            "joined": datetime.now()
        })

def get_sponsors():
    return list(sponsors.find())

def check_sponsors(uid):
    sp_list = get_sponsors()
    if not sp_list:
        return True
    for sp in sp_list:
        try:
            member = bot.get_chat_member(sp["channel_id"], uid)
            if member.status in ["left", "kicked"]:
                return False
        except:
            pass
    return True

def sponsor_keyboard():
    kb = InlineKeyboardMarkup()
    for sp in get_sponsors():
        kb.add(InlineKeyboardButton(f"📢 {sp['title']}", url=sp["link"]))
    kb.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_sponsor"))
    return kb

def main_menu(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎬 Kino olish", callback_data="get_movie"),
        InlineKeyboardButton("📋 Barcha kinolar", callback_data="all_movies")
    )
    if is_admin(uid):
        kb.add(InlineKeyboardButton("⚙️ Admin panel", callback_data="admin_panel"))
    return kb

def admin_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎬 Kino qo'shish", callback_data="add_movie"),
        InlineKeyboardButton("🗑 Kino o'chirish", callback_data="del_movie")
    )
    kb.add(
        InlineKeyboardButton("📊 Statistika", callback_data="stats"),
        InlineKeyboardButton("🎞 Kinolar", callback_data="movie_list")
    )
    kb.add(
        InlineKeyboardButton("👮 Admin qo'shish", callback_data="add_admin"),
        InlineKeyboardButton("❌ Admin o'chirish", callback_data="del_admin")
    )
    kb.add(
        InlineKeyboardButton("💰 Homiy qo'shish", callback_data="add_sponsor"),
        InlineKeyboardButton("🚫 Homiy o'chirish", callback_data="del_sponsor")
    )
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back_main"))
    return kb

def back_btn():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="back_main"))
    return kb

# === USER HOLATI ===
user_state = {}

# === START ===
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    add_user(uid, message.from_user.username, message.from_user.first_name)
    
    if not check_sponsors(uid):
        bot.send_message(uid, "⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=sponsor_keyboard())
        return
    
    args = message.text.split()
    if len(args) > 1:
        send_movie_by_code(message, args[1])
        return
    
    bot.send_message(uid,
        f"🎬 <b>Kino Botga xush kelibsiz!</b>\n\nSalom, <b>{message.from_user.first_name}</b>!\n\nKino kodini yuboring:",
        parse_mode="HTML",
        reply_markup=main_menu(uid)
    )

# === OBUNA TEKSHIRISH ===
@bot.callback_query_handler(func=lambda c: c.data == "check_sponsor")
def check_sponsor_cb(call):
    uid = call.from_user.id
    if not check_sponsors(uid):
        bot.answer_callback_query(call.id, "❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    bot.edit_message_text("✅ Obuna tasdiqlandi!", uid, call.message.message_id, reply_markup=main_menu(uid))

# === KINO YUBORISH ===
def send_movie_by_code(message, code):
    uid = message.from_user.id
    movie = movies.find_one({"code": code.upper()})
    if not movie:
        bot.send_message(uid, "❌ Bunday kodli kino topilmadi!")
        return
    movies.update_one({"code": code.upper()}, {"$inc": {"views": 1}})
    caption = f"🎬 <b>{movie['title']}</b>\n📋 Kod: <code>{movie['code']}</code>"
    try:
        bot.copy_message(uid, movie["chat_id"], movie["message_id"], caption=caption, parse_mode="HTML")
    except:
        bot.forward_message(uid, movie["chat_id"], movie["message_id"])

@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
def handle_text(message):
    uid = message.from_user.id
    state = user_state.get(uid)
    
    if not check_sponsors(uid):
        bot.send_message(uid, "⚠️ Avval obuna bo'ling:", reply_markup=sponsor_keyboard())
        return

    if state == "add_movie_code":
        code = message.text.strip().upper()
        if movies.find_one({"code": code}):
            bot.send_message(uid, f"❌ {code} allaqachon bor! Boshqa kod:")
            return
        user_state[uid] = {"step": "add_movie_title", "code": code}
        bot.send_message(uid, f"✅ Kod: <b>{code}</b>\n\nKino nomini kiriting:", parse_mode="HTML")

    elif isinstance(state, dict) and state.get("step") == "add_movie_title":
        user_state[uid]["title"] = message.text.strip()
        user_state[uid]["step"] = "add_movie_file"
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("🆓 Bepul", callback_data="mstatus_free"),
            InlineKeyboardButton("💎 VIP", callback_data="mstatus_vip")
        )
        bot.send_message(uid, "Status tanlang:", reply_markup=kb)

    elif isinstance(state, dict) and state.get("step") == "add_movie_file":
        data = user_state.pop(uid)
        movies.insert_one({
            "code": data["code"],
            "title": data["title"],
            "status": data.get("status", "free"),
            "chat_id": message.chat.id,
            "message_id": message.message_id,
            "views": 0,
            "added": datetime.now()
        })
        bot.send_message(uid, f"✅ Kino qo'shildi!\nKod: <code>{data['code']}</code>", parse_mode="HTML", reply_markup=admin_keyboard())

    elif state == "del_movie":
        user_state.pop(uid)
        code = message.text.strip().upper()
        result = movies.delete_one({"code": code})
        if result.deleted_count:
            bot.send_message(uid, f"✅ {code} o'chirildi!", reply_markup=admin_keyboard())
        else:
            bot.send_message(uid, f"❌ {code} topilmadi!", reply_markup=admin_keyboard())

    elif state == "add_admin":
        user_state.pop(uid)
        try:
            new_uid = int(message.text.strip())
            admins.update_one({"uid": new_uid}, {"$set": {"uid": new_uid}}, upsert=True)
            bot.send_message(uid, f"✅ Admin qo'shildi: {new_uid}", reply_markup=admin_keyboard())
        except:
            bot.send_message(uid, "❌ Xato ID!", reply_markup=admin_keyboard())

    elif state == "del_admin":
        user_state.pop(uid)
        try:
            del_uid = int(message.text.strip())
            admins.delete_one({"uid": del_uid})
            bot.send_message(uid, f"✅ Admin o'chirildi: {del_uid}", reply_markup=admin_keyboard())
        except:
            bot.send_message(uid, "❌ Xato ID!", reply_markup=admin_keyboard())

    elif isinstance(state, dict) and state.get("step") == "add_sponsor_id":
        try:
            ch_id = int(message.text.strip())
            user_state[uid]["channel_id"] = ch_id
            user_state[uid]["step"] = "add_sponsor_link"
            bot.send_message(uid, "Kanal invite linkini kiriting (https://t.me/...):")
        except:
            bot.send_message(uid, "❌ Xato ID!")

    elif isinstance(state, dict) and state.get("step") == "add_sponsor_link":
        user_state[uid]["link"] = message.text.strip()
        user_state[uid]["step"] = "add_sponsor_title"
        bot.send_message(uid, "Kanal nomini kiriting:")

    elif isinstance(state, dict) and state.get("step") == "add_sponsor_title":
        data = user_state.pop(uid)
        needed = data.get("needed", 0)
        sponsors.insert_one({
            "channel_id": data["channel_id"],
            "link": data["link"],
            "title": message.text.strip(),
            "needed": needed,
            "current": 0
        })
        bot.send_message(uid, "✅ Homiy qo'shildi!", reply_markup=admin_keyboard())

    else:
        send_movie_by_code(message, message.text.strip())

# === CALLBACK HANDLER ===
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(call):
    uid = call.from_user.id
    data = call.data

    if data == "back_main":
        bot.edit_message_text(
            f"🎬 Asosiy menyu:",
            uid, call.message.message_id,
            reply_markup=main_menu(uid)
        )

    elif data == "get_movie":
        bot.edit_message_text("🎬 Kino kodini yuboring!\n\nMasalan: <code>KINO001</code>",
            uid, call.message.message_id, parse_mode="HTML", reply_markup=back_btn())

    elif data == "all_movies":
        mv_list = list(movies.find())
        if not mv_list:
            bot.answer_callback_query(call.id, "Hozircha kinolar yo'q!", show_alert=True)
            return
        text = "🎬 <b>Barcha kinolar:</b>\n\n"
        for m in mv_list:
            text += f"📽 {m['title']} — Kod: <code>{m['code']}</code> | 👁 {m.get('views',0)} marta\n"
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=back_btn())

    elif data == "admin_panel":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        bot.edit_message_text("⚙️ <b>Admin Panel</b>", uid, call.message.message_id,
            parse_mode="HTML", reply_markup=admin_keyboard())

    elif data == "stats":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        total_users = users.count_documents({})
        total_movies = movies.count_documents({})
        total_views = sum(m.get("views", 0) for m in movies.find())
        total_admins = admins.count_documents({})
        total_sponsors = sponsors.count_documents({})
        bot.edit_message_text(
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Foydalanuvchilar: {total_users}\n"
            f"🎬 Kinolar: {total_movies}\n"
            f"👁 Jami ko'rishlar: {total_views}\n"
            f"👮 Adminlar: {total_admins}\n"
            f"💰 Homiylar: {total_sponsors}",
            uid, call.message.message_id,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")
            )
        )

    elif data == "movie_list":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        mv_list = list(movies.find())
        if not mv_list:
            bot.answer_callback_query(call.id, "Kinolar yo'q!", show_alert=True)
            return
        text = "🎞 <b>Kinolar ro'yxati:</b>\n\n"
        for m in mv_list:
            text += f"🎬 {m['title']}\n📋 Kod: <code>{m['code']}</code> | 👁 {m.get('views',0)}\n\n"
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")
            ))

    elif data == "add_movie":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        user_state[uid] = "add_movie_code"
        bot.edit_message_text("🎬 Kino kodini kiriting (masalan: KINO001):",
            uid, call.message.message_id)

    elif data.startswith("mstatus_"):
        status = data.replace("mstatus_", "")
        if isinstance(user_state.get(uid), dict):
            user_state[uid]["status"] = status
            user_state[uid]["step"] = "add_movie_file"
            bot.edit_message_text("Endi kino faylini yuboring (video/rasm/xabar):",
                uid, call.message.message_id)

    elif data == "del_movie":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        user_state[uid] = "del_movie"
        bot.edit_message_text("🗑 O'chiriladigan kino kodini kiriting:",
            uid, call.message.message_id)

    elif data == "add_admin":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        user_state[uid] = "add_admin"
        bot.edit_message_text("👮 Yangi admin Telegram ID sini kiriting:",
            uid, call.message.message_id)

    elif data == "del_admin":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        adm_list = list(admins.find())
        if not adm_list:
            bot.answer_callback_query(call.id, "Adminlar yo'q!", show_alert=True)
            return
        kb = InlineKeyboardMarkup()
        for a in adm_list:
            kb.add(InlineKeyboardButton(f"❌ {a['uid']}", callback_data=f"rmadm_{a['uid']}"))
        kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel"))
        bot.edit_message_text("O'chiriladigan adminni tanlang:", uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("rmadm_"):
        del_uid = int(data.split("_")[1])
        admins.delete_one({"uid": del_uid})
        bot.answer_callback_query(call.id, "✅ Admin o'chirildi!", show_alert=True)
        bot.edit_message_text("⚙️ <b>Admin Panel</b>", uid, call.message.message_id,
            parse_mode="HTML", reply_markup=admin_keyboard())

    elif data == "add_sponsor":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("1️⃣ 1000 obunachi", callback_data="sp_1000"))
        kb.add(InlineKeyboardButton("5️⃣ 5000 obunachi", callback_data="sp_5000"))
        kb.add(InlineKeyboardButton("🔟 10000 obunachi", callback_data="sp_10000"))
        kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel"))
        bot.edit_message_text(
            "💰 <b>Homiy qo'shish</b>\n\nHomiy nechta obunachi uchun to'laydi?",
            uid, call.message.message_id, parse_mode="HTML", reply_markup=kb)

    elif data.startswith("sp_"):
        needed = int(data.split("_")[1])
        user_state[uid] = {"step": "add_sponsor_id", "needed": needed}
        bot.edit_message_text(
            f"✅ {needed} obunachi tanlandi!\n\nKanal ID sini kiriting (masalan: -1001234567890)\nBotni kanalga admin qiling!",
            uid, call.message.message_id)

    elif data == "del_sponsor":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
            return
        sp_list = list(sponsors.find())
        if not sp_list:
            bot.answer_callback_query(call.id, "Homiylar yo'q!", show_alert=True)
            return
        kb = InlineKeyboardMarkup()
        for sp in sp_list:
            kb.add(InlineKeyboardButton(f"🚫 {sp['title']}", callback_data=f"rmsp_{sp['channel_id']}"))
        kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel"))
        bot.edit_message_text("O'chiriladigan homiyni tanlang:", uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("rmsp_"):
        ch_id = int(data.split("_")[1])
        sponsors.delete_one({"channel_id": ch_id})
        bot.answer_callback_query(call.id, "✅ Homiy o'chirildi!", show_alert=True)
        bot.edit_message_text("⚙️ <b>Admin Panel</b>", uid, call.message.message_id,
            parse_mode="HTML", reply_markup=admin_keyboard())

# === ISHGA TUSHIRISH ===
print("Bot ishga tushdi!")
bot.infinity_polling()
