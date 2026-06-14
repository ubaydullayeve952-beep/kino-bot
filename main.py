import telebot
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

TOKEN = os.getenv("TOKEN", "8991054869:AAHeRKQ91FtfZb7I9Q1BJEnYPh1aUNfm42g")
ADMIN_ID = 8965276284
KANAL = "@uzbekcha_kinolarmi"
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://admin:ravshan0202@cluster0.8ncigsp.mongodb.net/?appName=Cluster0")

client = MongoClient(MONGO_URL)
db = client["kinodb"]
kinolar_col = db["kinolar"]
homiylar_col = db["homiylar"]
stat_col = db["statistika"]
adminlar_col = db["adminlar"]

bot = telebot.TeleBot(TOKEN)

def admin_mi(user_id):
    if user_id == ADMIN_ID:
        return True
    return adminlar_col.find_one({"user_id": user_id}) is not None

def adminlar_yuklash():
    return list(adminlar_col.find())

def kino_saqlash(kod, nomi, file_id, tip, qism=None):
    kinolar_col.update_one(
        {"kod": kod, "qism": qism},
        {"$set": {"kod": kod, "nomi": nomi, "file_id": file_id, "tip": tip, "qism": qism, "korishlar": 0}},
        upsert=True
    )

def kino_olish(kod):
    return list(kinolar_col.find({"kod": kod}))

def kino_ochir(kod):
    kinolar_col.delete_many({"kod": kod})

def korishlar_oshir(kod, qism=None):
    kinolar_col.update_one({"kod": kod, "qism": qism}, {"$inc": {"korishlar": 1}})

def barcha_kinolar():
    kodlar = kinolar_col.distinct("kod")
    result = {}
    for kod in kodlar:
        result[kod] = list(kinolar_col.find({"kod": kod}))
    return result

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

def obuna_tekshir(user_id):
    for kanal in homiylar_yuklash():
        try:
            member = bot.get_chat_member(kanal, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            pass
    return True

def obuna_tugmalari():
    tugmalar = InlineKeyboardMarkup()
    for kanal in homiylar_yuklash():
        tugmalar.add(InlineKeyboardButton(f"Obuna bo'lish {kanal}", url=f"https://t.me/{kanal[1:]}"))
    tugmalar.add(InlineKeyboardButton("Tekshirish ✅", callback_data="tekshir"))
    return tugmalar

def get_file_id(message):
    if message.video:
        return message.video.file_id, "video"
    elif message.document:
        return message.document.file_id, "document"
    elif message.animation:
        return message.animation.file_id, "animation"
    elif message.video_note:
        return message.video_note.file_id, "video_note"
    elif message.audio:
        return message.audio.file_id, "audio"
    elif message.photo:
        return message.photo[-1].file_id, "photo"
    return None, None

def kino_yuborish_user(chat_id, kino):
    file_id = kino["file_id"]
    tip = kino.get("tip", "video")
    kanal_matn = f"\n\n🎬 Yangi kinolar: {KANAL}"
    caption = kino["nomi"] + kanal_matn
    try:
        if tip == "document":
            bot.send_document(chat_id, file_id, caption=caption)
        elif tip == "animation":
            bot.send_animation(chat_id, file_id, caption=caption)
        elif tip == "audio":
            bot.send_audio(chat_id, file_id, caption=caption)
        else:
            bot.send_video(chat_id, file_id, caption=caption)
    except:
        try:
            bot.send_document(chat_id, file_id, caption=caption)
        except Exception as e:
            bot.send_message(chat_id, f"❌ Xato: {e}")

@bot.message_handler(commands=["start"])
def start(message):
    if admin_mi(message.from_user.id):
        admin_panel(message)
        return
    foydalanuvchi_qosh(message.from_user.id)
    homiylar = homiylar_yuklash()
    if homiylar and not obuna_tekshir(message.from_user.id):
        bot.send_message(message.chat.id, "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling!", reply_markup=obuna_tugmalari())
        return
    tugma = InlineKeyboardMarkup()
    tugma.add(InlineKeyboardButton("🎬 Kinolar kanali", url=f"https://t.me/{KANAL[1:]}"))
    bot.send_message(message.chat.id, "🎬 Kino Botga Xush Kelibsiz!\nKino kodini yuboring!", reply_markup=tugma)

@bot.message_handler(func=lambda m: m.text and m.text.isdigit() and not admin_mi(m.from_user.id))
def kino_yuborish(message):
    homiylar = homiylar_yuklash()
    if homiylar and not obuna_tekshir(message.from_user.id):
        bot.send_message(message.chat.id, "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling!", reply_markup=obuna_tugmalari())
        return
    stat = stat_yuklash()
    stat["sorovlar"] += 1
    stat_saqlash(stat)
    kod = int(message.text.strip())
    kinolar = kino_olish(kod)
    if not kinolar:
        bot.send_message(message.chat.id, f"❌ {kod} kodli kino topilmadi!\n\n🎬 Barcha kinolar: {KANAL}")
        return
    if len(kinolar) == 1 and kinolar[0].get("qism") is None:
        korishlar_oshir(kod)
        kino_yuborish_user(message.chat.id, kinolar[0])
    else:
        tugmalar = InlineKeyboardMarkup()
        for kino in sorted(kinolar, key=lambda x: x.get("qism") or 0):
            tugmalar.add(InlineKeyboardButton(
                f"📺 {kino['qism']}-qism",
                callback_data=f"qism_{kod}_{kino['qism']}"
            ))
        bot.send_message(message.chat.id, f"🎬 {kinolar[0]['nomi']}\nQism tanlang:", reply_markup=tugmalar)

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not admin_mi(message.from_user.id):
        bot.send_message(message.chat.id, "Ruxsat yo'q!")
        return
    tugmalar = InlineKeyboardMarkup()
    tugmalar.row(
        InlineKeyboardButton("➕ Kino Qo'shish", callback_data="kino_qosh"),
        InlineKeyboardButton("🗑 Kino O'chirish", callback_data="kino_ochir")
    )
    tugmalar.row(
        InlineKeyboardButton("📋 Barcha Kinolar", callback_data="kino_list"),
        InlineKeyboardButton("📊 Statistika", callback_data="statistika")
    )
    tugmalar.row(
        InlineKeyboardButton("➕ Homiy Qo'shish", callback_data="homiy_qosh"),
        InlineKeyboardButton("🗑 Homiy O'chirish", callback_data="homiy_ochir")
    )
    tugmalar.row(
        InlineKeyboardButton("📢 Post Yuborish", callback_data="post_yuborish"),
        InlineKeyboardButton("📋 Homiylar", callback_data="homiy_list")
    )
    tugmalar.row(
        InlineKeyboardButton("👤 Admin Qo'shish", callback_data="admin_qosh"),
        InlineKeyboardButton("🗑 Admin O'chirish", callback_data="admin_ochir")
    )
    tugmalar.row(InlineKeyboardButton("👥 Adminlar Ro'yxati", callback_data="admin_list"))
    bot.send_message(message.chat.id, "👑 Admin Panel", reply_markup=tugmalar)

# Har qanday media — admin uchun (kino qo'shish jarayonida)
@bot.message_handler(content_types=["video", "document", "animation", "video_note", "audio"])
def media_handler(message):
    if admin_mi(message.from_user.id):
        bot.forward_message(message.chat.id, message.chat.id, message.message_id)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("qism_"):
        parts = call.data.split("_")
        kod = int(parts[1])
        qism = int(parts[2])
        kino = kinolar_col.find_one({"kod": kod, "qism": qism})
        if kino:
            korishlar_oshir(kod, qism)
            kino_yuborish_user(call.message.chat.id, kino)
        return

    if call.data == "tekshir":
        if obuna_tekshir(call.from_user.id):
            tugma = InlineKeyboardMarkup()
            tugma.add(InlineKeyboardButton("🎬 Kinolar kanali", url=f"https://t.me/{KANAL[1:]}"))
            bot.send_message(call.message.chat.id, "✅ Rahmat! Endi botdan foydalanishingiz mumkin!", reply_markup=tugma)
        else:
            bot.answer_callback_query(call.id, "Hali obuna bo'lmadingiz!")
            bot.send_message(call.message.chat.id, "Barcha kanallarga obuna bo'ling!", reply_markup=obuna_tugmalari())
        return

    if not admin_mi(call.from_user.id):
        bot.answer_callback_query(call.id, "Ruxsat yo'q!")
        return

    if call.data == "kino_qosh":
        msg = bot.send_message(call.message.chat.id, "Kino kodini yozing (raqam):")
        bot.register_next_step_handler(msg, kino_kod_olish)

    elif call.data == "kino_ochir":
        msg = bot.send_message(call.message.chat.id, "O'chirish uchun kino kodini yozing:")
        bot.register_next_step_handler(msg, kino_ochirish_step)

    elif call.data == "kino_list":
        kinolar = barcha_kinolar()
        if not kinolar:
            bot.send_message(call.message.chat.id, "Kino yo'q.")
            return
        matn = "📋 Barcha Kinolar:\n\n"
        for kod, klist in kinolar.items():
            jami = sum(k.get("korishlar", 0) for k in klist)
            if len(klist) == 1 and klist[0].get("qism") is None:
                matn += f"{kod}. {klist[0]['nomi']} — 👁 {jami}\n"
            else:
                matn += f"{kod}. {klist[0]['nomi']} ({len(klist)} qism) — 👁 {jami}\n"
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "statistika":
        stat = stat_yuklash()
        kinolar = barcha_kinolar()
        jami_korishlar = sum(sum(k.get("korishlar", 0) for k in v) for v in kinolar.values())
        matn = (
            f"📊 Statistika:\n\n"
            f"👥 Foydalanuvchilar: {len(stat['foydalanuvchilar'])}\n"
            f"🎬 Kino so'rovlar: {stat['sorovlar']}\n"
            f"🎞 Kinolar soni: {len(kinolar)}\n"
            f"👁 Jami ko'rishlar: {jami_korishlar}\n"
            f"🤝 Homiylar: {len(homiylar_yuklash())}\n"
            f"👤 Adminlar: {adminlar_col.count_documents({})}"
        )
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "post_yuborish":
        msg = bot.send_message(call.message.chat.id, "📢 Post matnini yozing:")
        bot.register_next_step_handler(msg, post_matn_olish)

    elif call.data == "homiy_qosh":
        msg = bot.send_message(call.message.chat.id, "Homiy kanal username:\nMisol: @kanal_nomi")
        bot.register_next_step_handler(msg, homiy_qoshish)

    elif call.data == "homiy_ochir":
        homiylar = homiylar_yuklash()
        if not homiylar:
            bot.send_message(call.message.chat.id, "Homiy yo'q.")
            return
        matn = "Homiylar:\n\n" + "\n".join(f"{i+1}. {h}" for i, h in enumerate(homiylar)) + "\n\nRaqamini yozing:"
        msg = bot.send_message(call.message.chat.id, matn)
        bot.register_next_step_handler(msg, homiy_ochirish)

    elif call.data == "homiy_list":
        homiylar = homiylar_yuklash()
        if not homiylar:
            bot.send_message(call.message.chat.id, "Homiy yo'q.")
            return
        matn = "🤝 Homiylar:\n\n" + "\n".join(f"{i+1}. {h}" for i, h in enumerate(homiylar))
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "admin_qosh":
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Faqat bosh admin qo'sha oladi!")
            return
        msg = bot.send_message(call.message.chat.id, "Yangi admin user_id ni yozing:")
        bot.register_next_step_handler(msg, admin_qoshish)

    elif call.data == "admin_ochir":
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Faqat bosh admin o'chira oladi!")
            return
        adminlar = adminlar_yuklash()
        if not adminlar:
            bot.send_message(call.message.chat.id, "Qo'shimcha admin yo'q.")
            return
        matn = "Adminlar:\n\n" + "\n".join(f"{i+1}. {a['user_id']}" for i, a in enumerate(adminlar)) + "\n\nRaqamini yozing:"
        msg = bot.send_message(call.message.chat.id, matn)
        bot.register_next_step_handler(msg, admin_ochirish)

    elif call.data == "admin_list":
        adminlar = adminlar_yuklash()
        matn = f"👤 Bosh admin: {ADMIN_ID}\n\n"
        if adminlar:
            matn += "Qo'shimcha adminlar:\n" + "\n".join(f"{i+1}. {a['user_id']}" for i, a in enumerate(adminlar))
        else:
            matn += "Qo'shimcha admin yo'q."
        bot.send_message(call.message.chat.id, matn)

def kino_kod_olish(message):
    try:
        kod = int(message.text.strip())
        msg = bot.send_message(message.chat.id, "Qismli kinomi?\n1 - Ha\n2 - Yo'q")
        bot.register_next_step_handler(msg, lambda m: qismli_mi(m, kod))
    except:
        bot.send_message(message.chat.id, "❌ Raqam kiriting!")

def qismli_mi(message, kod):
    if message.text and message.text.strip() == "1":
        msg = bot.send_message(message.chat.id, "Necha qism?")
        bot.register_next_step_handler(msg, lambda m: qism_soni_olish(m, kod))
    else:
        msg = bot.send_message(message.chat.id, "Kino nomini yozing:")
        bot.register_next_step_handler(msg, lambda m: kino_nom_olish(m, kod, None))

def qism_soni_olish(message, kod):
    try:
        soni = int(message.text.strip())
        msg = bot.send_message(message.chat.id, "Kino nomini yozing:")
        bot.register_next_step_handler(msg, lambda m: qismli_nom_olish(m, kod, soni, 1))
    except:
        bot.send_message(message.chat.id, "❌ Raqam kiriting!")

def qismli_nom_olish(message, kod, jami, joriy):
    nomi = message.text.strip()
    msg = bot.send_message(message.chat.id, f"{joriy}-qism videosini yuboring:")
    bot.register_next_step_handler(msg, lambda m: qismli_video_olish(m, kod, nomi, jami, joriy))

def qismli_video_olish(message, kod, nomi, jami, joriy):
    file_id, tip = get_file_id(message)
    if file_id:
        kino_saqlash(kod, nomi, file_id, tip, joriy)
        bot.send_message(message.chat.id, f"✅ {joriy}-qism saqlandi!")
        if joriy < jami:
            msg = bot.send_message(message.chat.id, f"{joriy+1}-qism videosini yuboring:")
            bot.register_next_step_handler(msg, lambda m: qismli_video_olish(m, kod, nomi, jami, joriy+1))
        else:
            bot.send_message(message.chat.id, f"✅ Barcha {jami} qism saqlandi! Kod: {kod}")
    else:
        msg = bot.send_message(message.chat.id, f"❌ Video yuboring! (tur: {message.content_type})")
        bot.register_next_step_handler(msg, lambda m: qismli_video_olish(m, kod, nomi, jami, joriy))

def kino_nom_olish(message, kod, qism):
    nomi = message.text.strip()
    msg = bot.send_message(message.chat.id, "Video yuboring (forward ham bo'ladi):")
    bot.register_next_step_handler(msg, lambda m: kino_video_olish(m, kod, nomi, qism))

def kino_video_olish(message, kod, nomi, qism):
    file_id, tip = get_file_id(message)
    if file_id:
        kino_saqlash(kod, nomi, file_id, tip, qism)
        bot.send_message(message.chat.id, f"✅ Kino qo'shildi!\nKod: {kod}\nNom: {nomi}")
    else:
        msg = bot.send_message(message.chat.id, f"❌ Video topilmadi (tur: {message.content_type})\nQaytadan yuboring:")
        bot.register_next_step_handler(msg, lambda m: kino_video_olish(m, kod, nomi, qism))

def kino_ochirish_step(message):
    try:
        kod = int(message.text.strip())
        if kino_olish(kod):
            kino_ochir(kod)
            bot.send_message(message.chat.id, f"✅ {kod} kodli kino o'chirildi!")
        else:
            bot.send_message(message.chat.id, f"❌ {kod} kodli kino topilmadi!")
    except:
        bot.send_message(message.chat.id, "❌ Raqam kiriting!")

def post_matn_olish(message):
    if message.photo:
        try:
            bot.send_photo(KANAL, message.photo[-1].file_id, caption=message.caption or "")
            bot.send_message(message.chat.id, "✅ Post yuborildi!")
        except:
            bot.send_message(message.chat.id, "❌ Xato!")
    elif message.video:
        try:
            bot.send_video(KANAL, message.video.file_id, caption=message.caption or "")
            bot.send_message(message.chat.id, "✅ Post yuborildi!")
        except:
            bot.send_message(message.chat.id, "❌ Xato!")
    elif message.text:
        try:
            bot.send_message(KANAL, message.text)
            bot.send_message(message.chat.id, "✅ Post yuborildi!")
        except:
            bot.send_message(message.chat.id, "❌ Xato!")
    else:
        bot.send_message(message.chat.id, "❌ Faqat matn, rasm yoki video!")

def homiy_qoshish(message):
    kanal = message.text.strip()
    if not kanal.startswith("@"):
        kanal = "@" + kanal
    if kanal not in homiylar_yuklash():
        homiy_saqlash(kanal)
        bot.send_message(message.chat.id, f"✅ {kanal} qo'shildi!")
    else:
        bot.send_message(message.chat.id, f"❌ {kanal} allaqachon bor!")

def homiy_ochirish(message):
    try:
        raqam = int(message.text.strip()) - 1
        homiylar = homiylar_yuklash()
        if 0 <= raqam < len(homiylar):
            homiy_ochir(homiylar[raqam])
            bot.send_message(message.chat.id, f"✅ {homiylar[raqam]} o'chirildi!")
        else:
            bot.send_message(message.chat.id, "❌ Bunday raqam yo'q!")
    except:
        bot.send_message(message.chat.id, "❌ Raqam kiriting!")

def admin_qoshish(message):
    try:
        user_id = int(message.text.strip())
        if adminlar_col.find_one({"user_id": user_id}):
            bot.send_message(message.chat.id, "❌ Allaqachon admin!")
        else:
            adminlar_col.insert_one({"user_id": user_id})
            bot.send_message(message.chat.id, f"✅ {user_id} admin qilindi!")
            try:
                bot.send_message(user_id, "✅ Siz admin qilindingiz!")
            except:
                pass
    except:
        bot.send_message(message.chat.id, "❌ Raqam kiriting!")

def admin_ochirish(message):
    try:
        raqam = int(message.text.strip()) - 1
        adminlar = adminlar_yuklash()
        if 0 <= raqam < len(adminlar):
            user_id = adminlar[raqam]["user_id"]
            adminlar_col.delete_one({"user_id": user_id})
            bot.send_message(message.chat.id, f"✅ {user_id} admin o'chirildi!")
        else:
            bot.send_message(message.chat.id, "❌ Bunday raqam yo'q!")
    except:
        bot.send_message(message.chat.id, "❌ Raqam kiriting!")

print("Bot ishlamoqda!")
bot.polling(none_stop=True)
