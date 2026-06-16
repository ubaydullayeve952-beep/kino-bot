import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# === SOZLAMALAR ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 8443))

# === JSON FAYL YO'LLARI ===
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
MOVIES_FILE = DATA_DIR / "movies.json"
ADMINS_FILE = DATA_DIR / "admins.json"
SPONSORS_FILE = DATA_DIR / "sponsors.json"
REQUESTS_FILE = DATA_DIR / "requests.json"

# === JSON YORDAMCHI ===

def load(file: Path):
    if not file.exists():
        file.write_text("[]")
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except:
        return []

def save(file: Path, data):
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# === HOLATLAR ===
(ADD_MOVIE_CODE, ADD_MOVIE_NAME, ADD_MOVIE_FILE,
 ADD_ADMIN, DEL_ADMIN, DEL_MOVIE,
 ADD_SPONSOR_NAME, ADD_SPONSOR_LINK,
 DEL_SPONSOR_INPUT,
 ADD_SUB_USER, ADD_SUB_TYPE) = range(11)

# === YORDAMCHI ===

def is_admin(user_id):
    admins = load(ADMINS_FILE)
    return any(a["user_id"] == user_id for a in admins)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Kino qo'shish", callback_data="add_movie"),
         InlineKeyboardButton("🎞 Kinolar", callback_data="list_movies")],
        [InlineKeyboardButton("🗑 Kino o'chirish", callback_data="del_movie"),
         InlineKeyboardButton("👤 Admin qo'shish", callback_data="add_admin")],
        [InlineKeyboardButton("👥 Adminlar", callback_data="list_admins"),
         InlineKeyboardButton("❌ Admin o'chirish", callback_data="del_admin")],
        [InlineKeyboardButton("📊 Statistika", callback_data="statistics")],
        [InlineKeyboardButton("🤝 Homiy qo'shish", callback_data="add_sponsor"),
         InlineKeyboardButton("📋 Homiylar", callback_data="list_sponsors")],
        [InlineKeyboardButton("🗑 Homiy o'chirish", callback_data="del_sponsor")],
        [InlineKeyboardButton("👑 Obunachi qo'shish", callback_data="add_sub_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sub_menu():
    keyboard = [
        [InlineKeyboardButton("💰 1000 obunachi", callback_data="sub_1000")],
        [InlineKeyboardButton("💎 5000 obunachi", callback_data="sub_5000")],
        [InlineKeyboardButton("🏆 10000 obunachi", callback_data="sub_10000")],
        [InlineKeyboardButton("⭐ VIP obunachi", callback_data="sub_vip")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Panel", callback_data="admin_panel")]])

async def check_subscription(user_id, context):
    sponsors = load(SPONSORS_FILE)
    for sponsor in sponsors:
        try:
            member = await context.bot.get_chat_member(
                chat_id=sponsor["link"], user_id=user_id
            )
            if member.status in ["left", "kicked"]:
                return False, sponsor
        except:
            continue
    return True, None

# === /start ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    users = load(USERS_FILE)
    if not any(u["user_id"] == uid for u in users):
        users.append({
            "user_id": uid,
            "username": user.username,
            "full_name": user.full_name,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sub_type": None
        })
        save(USERS_FILE, users)

    if is_admin(uid):
        await update.message.reply_text(
            "👋 Xush kelibsiz, Admin!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")]
            ])
        )
        return

    subscribed, sponsor = await check_subscription(uid, context)
    if not subscribed:
        link = sponsor["link"].replace("@", "")
        keyboard = [
            [InlineKeyboardButton(f"📢 {sponsor['name']}ga obuna bo'lish", url=f"https://t.me/{link}")],
            [InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await update.message.reply_text(
        "🎬 Salom! Kino kodini yuboring:\n\nMasalan: <code>101</code>",
        parse_mode="HTML"
    )

# === OBUNA TEKSHIRISH ===

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    subscribed, sponsor = await check_subscription(uid, context)
    if subscribed:
        await query.edit_message_text(
            "✅ Rahmat! Endi kino kodini yuboring.",
        )
    else:
        link = sponsor["link"].replace("@", "")
        keyboard = [
            [InlineKeyboardButton(f"📢 {sponsor['name']}ga obuna bo'lish", url=f"https://t.me/{link}")],
            [InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")]
        ]
        await query.edit_message_text(
            "❌ Hali obuna bo'lmadingiz:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# === KINO SO'ROVI (foydalanuvchi kod yuboradi) ===

async def handle_movie_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if is_admin(uid):
        return

    subscribed, sponsor = await check_subscription(uid, context)
    if not subscribed:
        link = sponsor["link"].replace("@", "")
        keyboard = [
            [InlineKeyboardButton(f"📢 {sponsor['name']}ga obuna bo'lish", url=f"https://t.me/{link}")],
            [InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "⚠️ Avval kanalga obuna bo'ling:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    movies = load(MOVIES_FILE)
    movie = next((m for m in movies if m["code"] == text), None)

    reqs = load(REQUESTS_FILE)
    reqs.append({
        "user_id": uid,
        "code": text,
        "found": movie is not None,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save(REQUESTS_FILE, reqs)

    if not movie:
        await update.message.reply_text("❌ Bunday kodli kino topilmadi.")
        return

    caption = f"🎬 <b>{movie['name']}</b>\n🔢 Kod: <code>{movie['code']}</code>"

    if movie["file_type"] == "video":
        await update.message.reply_video(
            video=movie["file_id"],
            caption=caption,
            parse_mode="HTML"
        )
    else:
        await update.message.reply_document(
            document=movie["file_id"],
            caption=caption,
            parse_mode="HTML"
        )

# === ADMIN PANEL ===

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    await query.edit_message_text("⚙️ Admin Panel:", reply_markup=get_main_menu())

# === KINO QO'SHISH ===

async def add_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🎬 Kino kodini kiriting (masalan: 101):")
    return ADD_MOVIE_CODE

async def add_movie_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    movies = load(MOVIES_FILE)
    if any(m["code"] == code for m in movies):
        await update.message.reply_text("⚠️ Bu kod allaqachon mavjud. Boshqa kod kiriting:")
        return ADD_MOVIE_CODE
    context.user_data["movie_code"] = code
    await update.message.reply_text("📝 Kino nomini kiriting:")
    return ADD_MOVIE_NAME

async def add_movie_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["movie_name"] = update.message.text.strip()
    await update.message.reply_text("📤 Kino faylini yuboring (video yoki fayl):")
    return ADD_MOVIE_FILE

async def add_movie_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    code = context.user_data.get("movie_code")
    name = context.user_data.get("movie_name")
    file_id = file_type = None

    if msg.video:
        file_id = msg.video.file_id
        file_type = "video"
    elif msg.document:
        file_id = msg.document.file_id
        file_type = "document"

    if not file_id:
        await msg.reply_text("❌ Fayl yuborilmadi. Qaytadan yuboring:")
        return ADD_MOVIE_FILE

    movies = load(MOVIES_FILE)
    movies.append({
        "code": code,
        "name": name,
        "file_id": file_id,
        "file_type": file_type,
        "added": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save(MOVIES_FILE, movies)

    await msg.reply_text(
        f"✅ Kino qo'shildi!\n🔢 Kod: <code>{code}</code>\n🎬 Nom: {name}",
        parse_mode="HTML",
        reply_markup=back_btn()
    )
    return ConversationHandler.END

# === KINOLAR RO'YXATI ===

async def list_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    movies = load(MOVIES_FILE)
    if not movies:
        await query.edit_message_text("📭 Kinolar yo'q.", reply_markup=back_btn())
        return
    text = "🎞 Kinolar:\n\n"
    for m in movies[-20:]:
        text += f"🔢 <code>{m['code']}</code> — {m['name']}\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_btn())

# === KINO O'CHIRISH ===

async def del_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🗑 O'chirmoqchi bo'lgan kino kodini kiriting:")
    return DEL_MOVIE

async def del_movie_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    movies = load(MOVIES_FILE)
    new_movies = [m for m in movies if m["code"] != code]
    if len(new_movies) == len(movies):
        await update.message.reply_text("❌ Bunday kodli kino topilmadi.")
        return DEL_MOVIE
    save(MOVIES_FILE, new_movies)
    await update.message.reply_text(
        f"✅ <code>{code}</code> kodli kino o'chirildi.",
        parse_mode="HTML", reply_markup=back_btn()
    )
    return ConversationHandler.END

# === ADMIN QO'SHISH ===

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("👤 Yangi admin ID sini kiriting:")
    return ADD_ADMIN

async def add_admin_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_id = int(update.message.text.strip())
        admins = load(ADMINS_FILE)
        if any(a["user_id"] == new_id for a in admins):
            await update.message.reply_text("⚠️ Bu foydalanuvchi allaqachon admin.")
            return ConversationHandler.END
        admins.append({"user_id": new_id, "added": datetime.now().strftime("%Y-%m-%d %H:%M")})
        save(ADMINS_FILE, admins)
        await update.message.reply_text(
            f"✅ Admin qo'shildi: <code>{new_id}</code>",
            parse_mode="HTML", reply_markup=back_btn()
        )
    except:
        await update.message.reply_text("❌ Noto'g'ri ID. Qaytadan kiriting:")
        return ADD_ADMIN
    return ConversationHandler.END

# === ADMINLAR RO'YXATI ===

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admins = load(ADMINS_FILE)
    if not admins:
        await query.edit_message_text("📭 Adminlar yo'q.", reply_markup=back_btn())
        return
    text = "👥 Adminlar:\n\n"
    for a in admins:
        text += f"🆔 <code>{a['user_id']}</code>\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_btn())

# === ADMIN O'CHIRISH ===

async def del_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ O'chirmoqchi bo'lgan admin ID sini kiriting:")
    return DEL_ADMIN

async def del_admin_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        del_id = int(update.message.text.strip())
        admins = load(ADMINS_FILE)
        new_admins = [a for a in admins if a["user_id"] != del_id]
        if len(new_admins) == len(admins):
            await update.message.reply_text("❌ Bunday admin topilmadi.")
            return DEL_ADMIN
        save(ADMINS_FILE, new_admins)
        await update.message.reply_text(
            f"✅ Admin o'chirildi: <code>{del_id}</code>",
            parse_mode="HTML", reply_markup=back_btn()
        )
    except:
        await update.message.reply_text("❌ Noto'g'ri ID.")
        return DEL_ADMIN
    return ConversationHandler.END

# === STATISTIKA ===

async def statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    users = load(USERS_FILE)
    movies = load(MOVIES_FILE)
    reqs = load(REQUESTS_FILE)
    admins = load(ADMINS_FILE)
    sponsors = load(SPONSORS_FILE)

    sub_1000 = sum(1 for u in users if u.get("sub_type") == "1000")
    sub_5000 = sum(1 for u in users if u.get("sub_type") == "5000")
    sub_10000 = sum(1 for u in users if u.get("sub_type") == "10000")
    sub_vip = sum(1 for u in users if u.get("sub_type") == "vip")
    found_reqs = sum(1 for r in reqs if r.get("found"))

    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{len(users)}</b>\n"
        f"🎬 Jami kinolar: <b>{len(movies)}</b>\n"
        f"📩 Kino so'rovlar: <b>{len(reqs)}</b>\n"
        f"✅ Topilgan so'rovlar: <b>{found_reqs}</b>\n"
        f"❌ Topilmagan: <b>{len(reqs) - found_reqs}</b>\n"
        f"👤 Adminlar: <b>{len(admins)}</b>\n"
        f"🤝 Homiylar: <b>{len(sponsors)}</b>\n\n"
        f"<b>💳 Obunachi turlari:</b>\n"
        f"💰 1000: <b>{sub_1000}</b>\n"
        f"💎 5000: <b>{sub_5000}</b>\n"
        f"🏆 10000: <b>{sub_10000}</b>\n"
        f"⭐ VIP: <b>{sub_vip}</b>"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_btn())

# === HOMIY QO'SHISH ===

async def add_sponsor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🤝 Homiy nomini kiriting:")
    return ADD_SPONSOR_NAME

async def add_sponsor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sponsor_name"] = update.message.text.strip()
    await update.message.reply_text("🔗 Kanal username kiriting (@username):")
    return ADD_SPONSOR_LINK

async def add_sponsor_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if not link.startswith("@"):
        link = "@" + link
    sponsors = load(SPONSORS_FILE)
    sponsors.append({
        "name": context.user_data["sponsor_name"],
        "link": link,
        "added": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save(SPONSORS_FILE, sponsors)
    await update.message.reply_text(
        f"✅ Homiy qo'shildi!\n🤝 {context.user_data['sponsor_name']}\n🔗 {link}",
        reply_markup=back_btn()
    )
    return ConversationHandler.END

# === HOMIYLAR RO'YXATI ===

async def list_sponsors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sponsors = load(SPONSORS_FILE)
    if not sponsors:
        await query.edit_message_text("📭 Homiylar yo'q.", reply_markup=back_btn())
        return
    text = "📋 Homiylar:\n\n"
    for s in sponsors:
        text += f"🤝 {s['name']} — {s['link']}\n"
    await query.edit_message_text(text, reply_markup=back_btn())

# === HOMIY O'CHIRISH ===

async def del_sponsor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sponsors = load(SPONSORS_FILE)
    if not sponsors:
        await query.edit_message_text("📭 O'chirish uchun homiylar yo'q.", reply_markup=back_btn())
        return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton(f"🗑 {s['name']}", callback_data=f"delsponsor_{s['link']}")]
        for s in sponsors
    ]
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_panel")])
    await query.edit_message_text("🗑 O'chirish uchun homiyni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DEL_SPONSOR_INPUT

async def del_sponsor_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    link = query.data.replace("delsponsor_", "")
    sponsors = load(SPONSORS_FILE)
    new_sponsors = [s for s in sponsors if s["link"] != link]
    save(SPONSORS_FILE, new_sponsors)
    await query.edit_message_text(f"✅ {link} homiydan o'chirildi.", reply_markup=back_btn())
    return ConversationHandler.END

# === OBUNACHI QO'SHISH ===

async def add_sub_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("👑 Obunachi turini tanlang:", reply_markup=get_sub_menu())

async def add_sub_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub_map = {
        "sub_1000": "1000",
        "sub_5000": "5000",
        "sub_10000": "10000",
        "sub_vip": "vip"
    }
    sub_type = sub_map.get(query.data)
    context.user_data["sub_type"] = sub_type
    await query.edit_message_text(
        f"👤 {sub_type} obunachi qo'shish uchun foydalanuvchi ID sini kiriting:"
    )
    return ADD_SUB_USER

async def add_sub_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        sub_type = context.user_data.get("sub_type")
        users = load(USERS_FILE)
        found = False
        for u in users:
            if u["user_id"] == uid:
                u["sub_type"] = sub_type
                found = True
                break
        if not found:
            users.append({
                "user_id": uid,
                "username": None,
                "full_name": None,
                "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sub_type": sub_type
            })
        save(USERS_FILE, users)
        labels = {"1000": "💰 1000", "5000": "💎 5000", "10000": "🏆 10000", "vip": "⭐ VIP"}
        await update.message.reply_text(
            f"✅ Foydalanuvchi <code>{uid}</code> → {labels.get(sub_type, sub_type)} obunachiga qo'shildi.",
            parse_mode="HTML", reply_markup=back_btn()
        )
    except:
        await update.message.reply_text("❌ Noto'g'ri ID. Qaytadan kiriting:")
        return ADD_SUB_USER
    return ConversationHandler.END

# === ASOSIY ===

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handlers
    conv_add_movie = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_movie_start, pattern="^add_movie$")],
        states={
            ADD_MOVIE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie_code)],
            ADD_MOVIE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie_name)],
            ADD_MOVIE_FILE: [MessageHandler(filters.VIDEO | filters.Document.ALL, add_movie_file)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    conv_del_movie = ConversationHandler(
        entry_points=[CallbackQueryHandler(del_movie_start, pattern="^del_movie$")],
        states={
            DEL_MOVIE: [MessageHandler(filters.TEXT & ~filters.COMMAND, del_movie_do)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    conv_add_admin = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^add_admin$")],
        states={
            ADD_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_do)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    conv_del_admin = ConversationHandler(
        entry_points=[CallbackQueryHandler(del_admin_start, pattern="^del_admin$")],
        states={
            DEL_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, del_admin_do)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    conv_add_sponsor = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_sponsor_start, pattern="^add_sponsor$")],
        states={
            ADD_SPONSOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sponsor_name)],
            ADD_SPONSOR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sponsor_link)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    conv_del_sponsor = ConversationHandler(
        entry_points=[CallbackQueryHandler(del_sponsor_start, pattern="^del_sponsor$")],
        states={
            DEL_SPONSOR_INPUT: [CallbackQueryHandler(del_sponsor_do, pattern="^delsponsor_")],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    conv_add_sub = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_sub_type, pattern="^sub_(1000|5000|10000|vip)$")],
        states={
            ADD_SUB_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sub_user)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Handlerlarni qo'shish
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_add_movie)
    app.add_handler(conv_del_movie)
    app.add_handler(conv_add_admin)
    app.add_handler(conv_del_admin)
    app.add_handler(conv_add_sponsor)
    app.add_handler(conv_del_sponsor)
    app.add_handler(conv_add_sub)

    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(list_movies, pattern="^list_movies$"))
    app.add_handler(CallbackQueryHandler(list_admins, pattern="^list_admins$"))
    app.add_handler(CallbackQueryHandler(list_sponsors, pattern="^list_sponsors$"))
    app.add_handler(CallbackQueryHandler(statistics, pattern="^statistics$"))
    app.add_handler(CallbackQueryHandler(add_sub_menu, pattern="^add_sub_menu$"))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_movie_request))

    # Railway uchun webhook, lokal uchun polling
    if WEBHOOK_URL:
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
        )
    else:
        print("Polling rejimida ishlamoqda...")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()oʻ
