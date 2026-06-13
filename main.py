import telebot
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

TOKEN = os.getenv("TOKEN", "8991054869:AAHeRKQ91FtfZb7I9Q1BJEnYPh1aUNfm42g")
ADMIN_ID = 8965276284
KANAL = "@uzbekcha_kinolarmi"
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://admin:ravshan0202@cluster0.8ncigsp.mongodb.net/?appName=Cluster0")

# MongoDB ulanish
client = MongoClient(MONGO_URL)
db = client["kinodb"]
kinolar_col = db["kinolar"]
homiylar_col = db["homiylar"]
stat_col = db["statistika"]

bot = telebot.TeleBot(TOKEN)

# --- MongoDB funksiyalar ---

def kinolar_yuklash():
    kinolar = {}
    for k in kinolar_col.find():
        kinolar[int(k["raqam"])] = {"nomi": k["nomi"], "file_id": k["file_id"], "tip": k["tip"]}
    return kinolar

def kino_saqlash(raqam, nomi, file_id, tip):
    kinolar_col.update_one(
        {"raqam": raqam},
        {"$set": {"raqam": raqam, "nomi": nomi, "file_id": file_id, "tip": tip}},
        upsert=True
    )

def kino_ochir(raqam):
    kinolar_col.delete_one({"raqam": raqam})

def homiylar_yuklash():
    return [h["kanal"] for h in homiylar_col.find()]

def homiy_saqlash(kanal):
    if not homiylar_col.find_one({"kanal": kanal}):
        homiylar_col.insert_one({"kanal": kanal})

def homiy_ochir(kanal):
    homiylar_col.delete_one({"kanal": kanal})

def stat_yuklash():
    s = stat_col.find_one({"_id": "stat"})
    if s:
        return s
    return {"_id": "stat", "foydalanuvchilar": [], "sorovlar": 0}

def stat_saqlash(stat):
    stat_col.update_one({"_id": "stat"}, {"$set": stat}, upsert=True)

def foydalanuvchi_qosh(user_id):
    stat = stat_yuklash()
    if str(user_id) not in stat["foydalanuvchilar"]:
        stat["foydalanuvchilar"].append(str(user_id))
        stat_saqlash(stat)

# --- Bot funksiyalar ---

def admin_mi(user_id):
    return user_id == ADMIN_ID

def obuna_tekshir(user_id):
    homiylar = homiylar_yuklash()
    for kanal in homiylar:
        try:
            member = bot.get_chat_member(kanal, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            pass
    return True

def obuna_tugmalari():
    homiylar = homiylar_yuklash()
    tugmalar = InlineKeyboardMarkup()
    for kanal in homiylar:
        tugmalar.add(InlineKeyboardButton(f"Obuna bolish {kanal}", url=f"https://t.me/{kanal[1:]}"))
    tugmalar.add(InlineKeyboardButton("Tekshirish ✅", callback_data="tekshir"))
    return tugmalar

@bot.message_handler(commands=["start"])
def start(message):
    if admin_mi(message.from_user.id):
        admin_panel(message)
        return
    foydalanuvchi_qosh(message.from_user.id)
    homiylar = homiylar_yuklash()
    if homiylar and not obuna_tekshir(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Botdan foydalanish uchun quyidagi kanallarga obuna boling!",
            reply_markup=obuna_tugmalari()
        )
        return
    tugma = InlineKeyboardMarkup()
    tugma.add(InlineKeyboardButton("🎬 Kinolar kanali", url=f"https://t.me/{KANAL[1:]}"))
    bot.send_message(
        message.chat.id,
        "🎬 Kino Botga Xush Kelibsiz!\nKino raqamini yuboring!",
        reply_markup=tugma
    )

@bot.message_handler(func=lambda m: m.text and m.text.isdigit() and not admin_mi(m.from_user.id))
def kino_yuborish(message):
    homiylar = homiylar_yuklash()
    if homiylar and not obuna_tekshir(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Botdan foydalanish uchun quyidagi kanallarga obuna boling!",
            reply_markup=obuna_tugmalari()
        )
        return
    stat = stat_yuklash()
    stat["sorovlar"] += 1
    stat_saqlash(stat)
    raqam = int(message.text.strip())
    kinolar = kinolar_yuklash()
    if raqam in kinolar:
        kino = kinolar[raqam]
        file_id = kino['file_id']
        tip = kino.get('tip', 'video')
        kanal_matn = f"\n\n🎬 Yangi kinolar: {KANAL}"
        try:
            if tip == 'document':
                bot.send_document(message.chat.id, file_id, caption=kino['nomi'] + kanal_matn)
            elif tip == 'animation':
                bot.send_animation(message.chat.id, file_id, caption=kino['nomi'] + kanal_matn)
            else:
                bot.send_video(message.chat.id, file_id, caption=kino['nomi'] + kanal_matn)
        except:
            bot.send_document(message.chat.id, file_id, caption=kino['nomi'] + kanal_matn)
    else:
        bot.send_message(
            message.chat.id,
            f"❌ {raqam} raqamli kino topilmadi!\n\n🎬 Barcha kinolar: {KANAL}"
        )

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not admin_mi(message.from_user.id):
        bot.send_message(message.chat.id, "Ruxsat yoq!")
        return
    tugmalar = InlineKeyboardMarkup()
    tugmalar.row(
        InlineKeyboardButton("➕ Kino Qoshish", callback_data="kino_qosh"),
        InlineKeyboardButton("🗑 Kino Ochirish", callback_data="kino_ochir")
    )
    tugmalar.row(
        InlineKeyboardButton("📋 Barcha Kinolar", callback_data="kino_list"),
        InlineKeyboardButton("📊 Statistika", callback_data="statistika")
    )
    tugmalar.row(
        InlineKeyboardButton("➕ Homiy Qoshish", callback_data="homiy_qosh"),
        InlineKeyboardButton("🗑 Homiy Ochirish", callback_data="homiy_ochir")
    )
    tugmalar.row(
        InlineKeyboardButton("📢 Post Yuborish", callback_data="post_yuborish"),
        InlineKeyboardButton("📋 Homiylar", callback_data="homiy_list")
    )
    bot.send_message(message.chat.id, "👑 Admin Panel", reply_markup=tugmalar)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "tekshir":
        if obuna_tekshir(call.from_user.id):
            tugma = InlineKeyboardMarkup()
            tugma.add(InlineKeyboardButton("🎬 Kinolar kanali", url=f"https://t.me/{KANAL[1:]}"))
            bot.send_message(call.message.chat.id, "✅ Rahmat! Endi botdan foydalanishingiz mumkin!", reply_markup=tugma)
        else:
            bot.answer_callback_query(call.id, "Hali obuna bolmadingiz!")
            bot.send_message(call.message.chat.id, "Barcha kanallarga obuna boling!", reply_markup=obuna_tugmalari())
        return

    if not admin_mi(call.from_user.id):
        bot.answer_callback_query(call.id, "Ruxsat yoq!")
        return

    if call.data == "kino_qosh":
        msg = bot.send_message(call.message.chat.id, "Kino raqamini yozing:")
        bot.register_next_step_handler(msg, kino_raqam_olish)

    elif call.data == "kino_ochir":
        kinolar = kinolar_yuklash()
        if not kinolar:
            bot.send_message(call.message.chat.id, "Kino yoq.")
            return
        msg = bot.send_message(call.message.chat.id, "Qaysi raqamni ochirish kerak?")
        bot.register_next_step_handler(msg, kino_ochirish)

    elif call.data == "kino_list":
        kinolar = kinolar_yuklash()
        if not kinolar:
            bot.send_message(call.message.chat.id, "Kino yoq.")
            return
        matn = "📋 Barcha Kinolar:\n\n"
        for raqam, kino in kinolar.items():
            matn += f"{raqam}. {kino['nomi']}\n"
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "statistika":
        stat = stat_yuklash()
        kinolar = kinolar_yuklash()
        homiylar = homiylar_yuklash()
        matn = (
            f"📊 Statistika:\n\n"
            f"👥 Foydalanuvchilar: {len(stat['foydalanuvchilar'])}\n"
            f"🎬 Kino sorovlar: {stat['sorovlar']}\n"
            f"🎞 Kinolar soni: {len(kinolar)}\n"
            f"🤝 Homiylar soni: {len(homiylar)}"
        )
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "post_yuborish":
        msg = bot.send_message(
            call.message.chat.id,
            "📢 Post matnini yozing:\n\n(Rasm yoki video bilan yubormoqchi bolsangiz, rasmga matn yozing)"
        )
        bot.register_next_step_handler(msg, post_matn_olish)

    elif call.data == "homiy_qosh":
        msg = bot.send_message(call.message.chat.id, "Homiy kanal username ini yozing:\nMisol: @kanal_nomi")
        bot.register_next_step_handler(msg, homiy_qoshish)

    elif call.data == "homiy_ochir":
        homiylar = homiylar_yuklash()
        if not homiylar:
            bot.send_message(call.message.chat.id, "Homiy yoq.")
            return
        matn = "Homiylar:\n\n"
        for i, h in enumerate(homiylar):
            matn += f"{i+1}. {h}\n"
        matn += "\nRaqamini yozing:"
        msg = bot.send_message(call.message.chat.id, matn)
        bot.register_next_step_handler(msg, homiy_ochirish)

    elif call.data == "homiy_list":
        homiylar = homiylar_yuklash()
        if not homiylar:
            bot.send_message(call.message.chat.id, "Homiy yoq.")
            return
        matn = "🤝 Homiylar:\n\n"
        for i, h in enumerate(homiylar):
            matn += f"{i+1}. {h}\n"
        bot.send_message(call.message.chat.id, matn)

def post_matn_olish(message):
    if message.photo:
        file_id = message.photo[-1].file_id
        matn = message.caption or ""
        try:
            bot.send_photo(KANAL, file_id, caption=matn)
            bot.send_message(message.chat.id, "✅ Post kanalga yuborildi!")
        except:
            bot.send_message(message.chat.id, "❌ Xato! Bot kanalda admin emasmi?")
    elif message.video:
        file_id = message.video.file_id
        matn = message.caption or ""
        try:
            bot.send_video(KANAL, file_id, caption=matn)
            bot.send_message(message.chat.id, "✅ Post kanalga yuborildi!")
        except:
            bot.send_message(message.chat.id, "❌ Xato! Bot kanalda admin emasmi?")
    elif message.text:
        try:
            bot.send_message(KANAL, message.text)
            bot.send_message(message.chat.id, "✅ Post kanalga yuborildi!")
        except:
            bot.send_message(message.chat.id, "❌ Xato! Bot kanalda admin emasmi?")
    else:
        bot.send_message(message.chat.id, "❌ Faqat matn, rasm yoki video yuboring!")

def kino_raqam_olish(message):
    try:
        raqam = int(message.text.strip())
        msg = bot.send_message(message.chat.id, f"Raqam: {raqam}\nKino nomini yozing:")
        bot.register_next_step_handler(msg, lambda m: kino_nom_olish(m, raqam))
    except:
        bot.send_message(message.chat.id, "Raqam kiriting!")

def kino_nom_olish(message, raqam):
    nomi = message.text.strip()
    msg = bot.send_message(message.chat.id, f"Nom: {nomi}\nEndi video yuboring:")
    bot.register_next_step_handler(msg, lambda m: kino_video_olish(m, raqam, nomi))

def kino_video_olish(message, raqam, nomi):
    file_id = None
    tip = None
    if message.video:
        file_id = message.video.file_id
        tip = "video"
    elif message.document:
        file_id = message.document.file_id
        tip = "document"
    elif message.animation:
        file_id = message.animation.file_id
        tip = "animation"
    elif message.video_note:
        file_id = message.video_note.file_id
        tip = "video_note"
    if file_id:
        kino_saqlash(raqam, nomi, file_id, tip)
        bot.send_message(message.chat.id, f"✅ Kino qoshildi!\nRaqam: {raqam}\nNomi: {nomi}")
    else:
        bot.send_message(message.chat.id, f"❌ Xato! Tur: {message.content_type}\nQaytadan yuboring!")

def kino_ochirish(message):
    try:
        raqam = int(message.text.strip())
        kinolar = kinolar_yuklash()
        if raqam in kinolar:
            nomi = kinolar[raqam]["nomi"]
            kino_ochir(raqam)
            bot.send_message(message.chat.id, f"✅ {nomi} ochirildi!")
        else:
            bot.send_message(message.chat.id, f"❌ {raqam} raqamli kino topilmadi!")
    except:
        bot.send_message(message.chat.id, "Raqam kiriting!")

def homiy_qoshish(message):
    kanal = message.text.strip()
    if not kanal.startswith("@"):
        kanal = "@" + kanal
    homiylar = homiylar_yuklash()
    if kanal not in homiylar:
        homiy_saqlash(kanal)
        bot.send_message(message.chat.id, f"✅ {kanal} homiy qoshildi!")
    else:
        bot.send_message(message.chat.id, f"❌ {kanal} allaqachon bor!")

def homiy_ochirish(message):
    try:
        raqam = int(message.text.strip()) - 1
        homiylar = homiylar_yuklash()
        if 0 <= raqam < len(homiylar):
            nomi = homiylar[raqam]
            homiy_ochir(nomi)
            bot.send_message(message.chat.id, f"✅ {nomi} ochirildi!")
        else:
            bot.send_message(message.chat.id, "❌ Bunday raqam yoq!")
    except:
        bot.send_message(message.chat.id, "Raqam kiriting!")

print("Bot ishlamoqda... MongoDB ulangan!")
bot.polling(none_stop=True)
