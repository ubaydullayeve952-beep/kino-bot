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
user_states = {}

def set_state(uid, state, data=None):
    user_states[uid] = {"state": state, "data": data or {}}

def get_state(uid):
    return user_states.get(uid, {})

def clear_state(uid):
    user_states.pop(uid, None)

def admin_mi(uid):
    if uid == ADMIN_ID:
        return True
    return adminlar_col.find_one({"user_id": uid}) is not None

def kino_saqlash(kod, nomi, file_id, tip, qism=None):
    kinolar_col.update_one(
        {"kod": kod, "qism": qism},
        {
            "$set": {"kod": kod, "nomi": nomi, "file_id": file_id, "tip": tip, "qism": qism},
            "$setOnInsert": {"korishlar": 0}
        },
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
    return s if s else {"_id": "stat", "foydalanuvchilar": [], "sorovlar": 0}

def stat_saqlash(stat):
    stat_col.update_one({"_id": "stat"}, {"$set": stat}, upsert=True)

def foydalanuvchi_qosh(uid):
    stat = stat_yuklash()
    if str(uid) not in stat["foydalanuvchilar"]:
        stat["foydalanuvchilar"].append(str(uid))
        stat_saqlash(stat)

def obuna_tekshir(uid):
    for kanal in homiylar_yuklash():
        try:
            member = bot.get_chat_member(kanal, uid)
            if member.status in ["left", "kicked"]:
                return False
        except:
            pass
    return True

def obuna_tugmalari():
    m = InlineKeyboardMarkup()
    for kanal in homiylar_yuklash():
        m.add(InlineKeyboardButton(f"✅ Obuna bo'lish: {kanal}", url=f"https://t.me/{kanal[1:]}"))
    m.add(InlineKeyboardButton("🔄 Tekshirish", callback_data="tekshir"))
    return m

def get_file_id(message):
    """Har qanday holatda file_id oladi — forward, caption bilan ham"""
    # 1. Oddiy video
    if message.video:
        return message.video.file_id, "video"
    # 2. Document (forward qilingan video document bo'lib kelishi mumkin)
    if message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("video"):
            return message.document.file_id, "video"
        return message.document.file_id, "document"
    # 3. Animation / GIF
    if message.animation:
        return message.animation.file_id, "animation"
    # 4. Video note (doira video)
    if message.video_note:
        return message.video_note.file_id, "video_note"
    # 5. Audio
    if message.audio:
        return message.audio.file_id, "audio"
    # 6. Rasm
    if message.photo:
        return message.photo[-1].file_id, "photo"
    # 7. JSON dan olish — yuklanmagan forward video uchun
    try:
        msg_json = message.json
        if "video" in msg_json:
            return msg_json["video"]["file_id"], "video"
        if "document" in msg_json:
            doc = msg_json["document"]
            mime = doc.get("mime_type", "")
            tip = "video" if mime.startswith("video") else "document"
            return doc["file_id"], tip
    except:
        pass
    return None, None

def send_kino(chat_id, kino):
    """Kinoni foydalanuvchiga yuboradi — faqat kino nomi, boshqa narsa yo'q"""
    file_id = kino["file_id"]
    tip = kino.get("tip", "video")
    # Faqat kino nomi va kanal — boshqa hech narsa yo'q
    caption = f"🎬 {kino['nomi']}\n\n📢 {KANAL}"
    try:
        if tip == "document":
            bot.send_document(chat_id, file_id, caption=caption)
        elif tip == "animation":
            bot.send_animation(chat_id, file_id, caption=caption)
        elif tip == "audio":
            bot.send_audio(chat_id, file_id, caption=caption)
        elif tip == "photo":
            bot.send_photo(chat_id, file_id, caption=caption)
        else:
            bot.send_video(chat_id, file_id, caption=caption)
    except Exception:
        try:
            bot.send_document(chat_id, file_id, caption=caption)
        except Exception as e:
            bot.send_message(chat_id, f"❌ Xato: {e}")

def admin_panel_yuborish(chat_id):
    m = InlineKeyboardMarkup()
    m.row(
        InlineKeyboardButton("➕ Kino Qo'shish", callback_data="kino_qosh"),
        InlineKeyboardButton("🗑 Kino O'chirish", callback_data="kino_ochir")
    )
    m.row(
        InlineKeyboardButton("📋 Barcha Kinolar", callback_data="kino_list"),
        InlineKeyboardButton("📊 Statistika", callback_data="statistika")
    )
    m.row(
        InlineKeyboardButton("➕ Homiy Qo'shish", callback_data="homiy_qosh"),
        InlineKeyboardButton("🗑 Homiy O'chirish", callback_data="homiy_ochir")
    )
    m.row(
        InlineKeyboardButton("📢 Post Yuborish", callback_data="post_yuborish"),
        InlineKeyboardButton("📋 Homiylar", callback_data="homiy_list")
    )
    m.row(
        InlineKeyboardButton("👤 Admin Qo'shish", callback_data="admin_qosh"),
        InlineKeyboardButton("🗑 Admin O'chirish", callback_data="admin_ochir")
    )
    m.row(InlineKeyboardButton("👥 Adminlar Ro'yxati", callback_data="admin_list"))
    bot.send_message(chat_id, "👑 Admin Panel", reply_markup=m)

@bot.message_handler(commands=["start"])
def start(msg):
    clear_state(msg.from_user.id)
    if admin_mi(msg.from_user.id):
        admin_panel_yuborish(msg.chat.id)
        return
    foydalanuvchi_qosh(msg.from_user.id)
    if homiylar_yuklash() and not obuna_tekshir(msg.from_user.id):
        bot.send_message(msg.chat.id, "⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling!", reply_markup=obuna_tugmalari())
        return
    m = InlineKeyboardMarkup()
    m.add(InlineKeyboardButton("🎬 Kinolar kanali", url=f"https://t.me/{KANAL[1:]}"))
    bot.send_message(msg.chat.id, "🎬 Kino Botga Xush Kelibsiz!\n\nKino kodini yuboring!", reply_markup=m)

@bot.message_handler(commands=["admin"])
def admin_cmd(msg):
    if not admin_mi(msg.from_user.id):
        bot.send_message(msg.chat.id, "❌ Ruxsat yo'q!")
        return
    clear_state(msg.from_user.id)
    admin_panel_yuborish(msg.chat.id)

@bot.message_handler(content_types=["text", "video", "document", "animation", "video_note", "audio", "photo"])
def universal(msg):
    uid = msg.from_user.id
    si = get_state(uid)
    state = si.get("state")
    data = si.get("data", {})

    # ── ODDIY FOYDALANUVCHI ──
    if not admin_mi(uid):
        if msg.text and msg.text.strip().isdigit():
            if homiylar_yuklash() and not obuna_tekshir(uid):
                bot.send_message(msg.chat.id, "⚠️ Avval kanallarga obuna bo'ling!", reply_markup=obuna_tugmalari())
                return
            stat = stat_yuklash()
            stat["sorovlar"] += 1
            stat_saqlash(stat)
            kod = int(msg.text.strip())
            kinolar = kino_olish(kod)
            if not kinolar:
                bot.send_message(msg.chat.id, f"❌ {kod} kodli kino topilmadi!\n\n🎬 Barcha kinolar: {KANAL}")
                return
            if len(kinolar) == 1 and kinolar[0].get("qism") is None:
                korishlar_oshir(kod)
                send_kino(msg.chat.id, kinolar[0])
            else:
                m = InlineKeyboardMarkup()
                for k in sorted(kinolar, key=lambda x: x.get("qism") or 0):
                    m.add(InlineKeyboardButton(f"📺 {k['qism']}-qism", callback_data=f"qism_{kod}_{k['qism']}"))
                bot.send_message(msg.chat.id, f"🎬 {kinolar[0]['nomi']}\nQism tanlang:", reply_markup=m)
        else:
            bot.send_message(msg.chat.id, "Kino kodini yuboring (faqat raqam)!")
        return

    # ── ADMIN STATE MACHINE ──
    if state == "kino_kod":
        if msg.text and msg.text.strip().isdigit():
            kod = int(msg.text.strip())
            set_state(uid, "kino_qismli", {"kod": kod})
            bot.send_message(msg.chat.id, "Qismli kinomi?\n\n1 - Ha\n2 - Yo'q")
        else:
            bot.send_message(msg.chat.id, "❌ Faqat raqam kiriting!")

    elif state == "kino_qismli":
        txt = msg.text.strip() if msg.text else ""
        if txt in ["1", "ha", "Ha", "HA"]:
            set_state(uid, "kino_qism_soni", data)
            bot.send_message(msg.chat.id, "Necha qism?")
        elif txt in ["2", "yo'q", "Yo'q", "yoq", "Yoq", "YO'Q", "no", "No"]:
            set_state(uid, "kino_nom", {**data, "qism": None})
            bot.send_message(msg.chat.id, "Kino nomini yozing:")
        else:
            bot.send_message(msg.chat.id, "❌ 1 yoki 2 yozing!\n\n1 - Ha\n2 - Yo'q")

    elif state == "kino_qism_soni":
        if msg.text and msg.text.strip().isdigit():
            soni = int(msg.text.strip())
            set_state(uid, "kino_qismli_nom", {**data, "jami": soni, "joriy": 1})
            bot.send_message(msg.chat.id, "Kino nomini yozing:")
        else:
            bot.send_message(msg.chat.id, "❌ Faqat raqam kiriting!")

    elif state == "kino_qismli_nom":
        nomi = msg.text.strip()
        set_state(uid, "kino_qismli_video", {**data, "nomi": nomi})
        bot.send_message(msg.chat.id, f"✅ Nom saqlandi!\n\n{data['joriy']}-qism videosini yuboring:")

    elif state == "kino_nom":
        nomi = msg.text.strip()
        set_state(uid, "kino_video", {**data, "nomi": nomi})
        bot.send_message(msg.chat.id, "✅ Nom saqlandi!\n\nVideo yuboring:")

    elif state == "kino_video":
        file_id, tip = get_file_id(msg)
        if file_id:
            kino_saqlash(data["kod"], data["nomi"], file_id, tip, data.get("qism"))
            clear_state(uid)
            bot.send_message(msg.chat.id, f"✅ Kino qo'shildi!\n\n📌 Kod: {data['kod']}\n🎬 Nom: {data['nomi']}\n📁 Tur: {tip}")
        else:
            bot.send_message(msg.chat.id, f"❌ Video topilmadi!\nKelgan tur: {msg.content_type}\n\nQaytadan yuboring:")

    elif state == "kino_qismli_video":
        file_id, tip = get_file_id(msg)
        if file_id:
            joriy = data["joriy"]
            jami = data["jami"]
            kino_saqlash(data["kod"], data["nomi"], file_id, tip, joriy)
            if joriy < jami:
                set_state(uid, "kino_qismli_video", {**data, "joriy": joriy + 1})
                bot.send_message(msg.chat.id, f"✅ {joriy}-qism saqlandi!\n\n{joriy+1}-qism videosini yuboring:")
            else:
                clear_state(uid)
                bot.send_message(msg.chat.id, f"✅ Barcha {jami} qism saqlandi!\n\n📌 Kod: {data['kod']}\n🎬 Nom: {data['nomi']}")
        else:
            bot.send_message(msg.chat.id, f"❌ Video topilmadi!\nKelgan tur: {msg.content_type}\n\nQaytadan yuboring:")

    elif state == "kino_ochir":
        if msg.text and msg.text.strip().isdigit():
            kod = int(msg.text.strip())
            if kino_olish(kod):
                kino_ochir(kod)
                clear_state(uid)
                bot.send_message(msg.chat.id, f"✅ {kod} kodli kino o'chirildi!")
            else:
                bot.send_message(msg.chat.id, f"❌ {kod} kodli kino topilmadi!")
        else:
            bot.send_message(msg.chat.id, "❌ Faqat raqam kiriting!")

    elif state == "post":
        try:
            if msg.photo:
                bot.send_photo(KANAL, msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.video:
                bot.send_video(KANAL, msg.video.file_id, caption=msg.caption or "")
            elif msg.document:
                bot.send_document(KANAL, msg.document.file_id, caption=msg.caption or "")
            elif msg.animation:
                bot.send_animation(KANAL, msg.animation.file_id, caption=msg.caption or "")
            elif msg.text:
                bot.send_message(KANAL, msg.text)
            else:
                bot.send_message(msg.chat.id, "❌ Faqat matn, rasm, video yoki document!")
                return
            bot.send_message(msg.chat.id, "✅ Post kanalga yuborildi!")
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Xato: {e}")
        clear_state(uid)

    elif state == "homiy_qosh":
        kanal = msg.text.strip() if msg.text else ""
        if not kanal:
            bot.send_message(msg.chat.id, "❌ Kanal nomini yozing!")
            return
        if not kanal.startswith("@"):
            kanal = "@" + kanal
        if kanal in homiylar_yuklash():
            bot.send_message(msg.chat.id, f"❌ {kanal} allaqachon mavjud!")
        else:
            homiy_saqlash(kanal)
            bot.send_message(msg.chat.id, f"✅ {kanal} qo'shildi!")
        clear_state(uid)

    elif state == "homiy_ochir":
        if msg.text and msg.text.strip().isdigit():
            raqam = int(msg.text.strip()) - 1
            homiylar = homiylar_yuklash()
            if 0 <= raqam < len(homiylar):
                homiy_ochir(homiylar[raqam])
                bot.send_message(msg.chat.id, f"✅ {homiylar[raqam]} o'chirildi!")
            else:
                bot.send_message(msg.chat.id, "❌ Bunday raqam yo'q!")
        else:
            bot.send_message(msg.chat.id, "❌ Faqat raqam kiriting!")
        clear_state(uid)

    elif state == "admin_qosh":
    if msg.text and msg.text.strip().isdigit():
        try:
            new_id = int(msg.text.strip())
            if new_id == ADMIN_ID:
                bot.send_message(msg.chat.id, "❌ Bu bosh admin!")
            elif adminlar_col.find_one({"user_id": new_id}):
                bot.send_message(msg.chat.id, "❌ Allaqachon admin!")
            else:
                adminlar_col.insert_one({"user_id": new_id})
                bot.send_message(msg.chat.id, f"✅ {new_id} admin qilindi!")
                try:
                    bot.send_message(new_id, "🎉 Siz admin qilindingiz!")
                except:
                    pass
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Xato: {e}")
    else:
        bot.send_message(msg.chat.id, "❌ Faqat raqam kiriting!")
    clear_state(uid)
            if new_id == ADMIN_ID:
                bot.send_message(msg.chat.id, "❌ Bu bosh admin!")
            elif adminlar_col.find_one({"user_id": new_id}):
                bot.send_message(msg.chat.id, "❌ Allaqachon admin!")
            else:
                adminlar_col.insert_one({"user_id": new_id})
                bot.send_message(msg.chat.id, f"✅ {new_id} admin qilindi!")
                try:
                    bot.send_message(new_id, "🎉 Siz admin qilindingiz!\n/admin yuboring.")
                except:
                    pass
        else:
            bot.send_message(msg.chat.id, "❌ Faqat user_id raqamini kiriting!")
        clear_state(uid)

    elif state == "admin_ochir":
        if msg.text and msg.text.strip().isdigit():
            raqam = int(msg.text.strip()) - 1
            adminlar = list(adminlar_col.find())
            if 0 <= raqam < len(adminlar):
                uid_ochir = adminlar[raqam]["user_id"]
                adminlar_col.delete_one({"user_id": uid_ochir})
                bot.send_message(msg.chat.id, f"✅ {uid_ochir} admin o'chirildi!")
            else:
                bot.send_message(msg.chat.id, "❌ Bunday raqam yo'q!")
        else:
            bot.send_message(msg.chat.id, "❌ Faqat raqam kiriting!")
        clear_state(uid)

    else:
        clear_state(uid)
        admin_panel_yuborish(msg.chat.id)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    uid = call.from_user.id

    if call.data.startswith("qism_"):
        parts = call.data.split("_")
        kod = int(parts[1])
        qism = int(parts[2])
        kino = kinolar_col.find_one({"kod": kod, "qism": qism})
        if kino:
            korishlar_oshir(kod, qism)
            send_kino(call.message.chat.id, kino)
        else:
            bot.send_message(call.message.chat.id, "❌ Kino topilmadi!")
        return

    if call.data == "tekshir":
        if obuna_tekshir(uid):
            m = InlineKeyboardMarkup()
            m.add(InlineKeyboardButton("🎬 Kinolar kanali", url=f"https://t.me/{KANAL[1:]}"))
            bot.send_message(call.message.chat.id, "✅ Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin!", reply_markup=m)
        else:
            bot.answer_callback_query(call.id, "❌ Hali obuna bo'lmadingiz!", show_alert=True)
            bot.send_message(call.message.chat.id, "⚠️ Barcha kanallarga obuna bo'ling!", reply_markup=obuna_tugmalari())
        return

    if not admin_mi(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!")
        return

    if call.data == "kino_qosh":
        set_state(uid, "kino_kod")
        bot.send_message(call.message.chat.id, "📌 Kino kodini yozing (raqam):")

    elif call.data == "kino_ochir":
        set_state(uid, "kino_ochir")
        bot.send_message(call.message.chat.id, "🗑 O'chirmoqchi bo'lgan kino kodini yozing:")

    elif call.data == "kino_list":
        kinolar = barcha_kinolar()
        if not kinolar:
            bot.send_message(call.message.chat.id, "📭 Hozircha kino yo'q.")
            return
        matn = "📋 Barcha Kinolar:\n\n"
        for kod, klist in sorted(kinolar.items()):
            jami = sum(k.get("korishlar", 0) for k in klist)
            if len(klist) == 1 and klist[0].get("qism") is None:
                matn += f"🎬 {kod} — {klist[0]['nomi']} | 👁 {jami}\n"
            else:
                matn += f"🎬 {kod} — {klist[0]['nomi']} ({len(klist)} qism) | 👁 {jami}\n"
        for i in range(0, len(matn), 4000):
            bot.send_message(call.message.chat.id, matn[i:i+4000])

    elif call.data == "statistika":
        stat = stat_yuklash()
        kinolar = barcha_kinolar()
        jami_korishlar = sum(sum(k.get("korishlar", 0) for k in v) for v in kinolar.values())
        matn = (
            f"📊 Bot Statistikasi:\n\n"
            f"👥 Foydalanuvchilar: {len(stat['foydalanuvchilar'])}\n"
            f"🔍 Kino so'rovlar: {stat['sorovlar']}\n"
            f"🎞 Kinolar soni: {len(kinolar)}\n"
            f"👁 Jami ko'rishlar: {jami_korishlar}\n"
            f"🤝 Homiylar: {len(homiylar_yuklash())}\n"
            f"👤 Adminlar: {adminlar_col.count_documents({})}"
        )
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "post_yuborish":
        set_state(uid, "post")
        bot.send_message(call.message.chat.id, "📢 Kanalga yubormoqchi bo'lgan postni yuboring:")

    elif call.data == "homiy_qosh":
        set_state(uid, "homiy_qosh")
        bot.send_message(call.message.chat.id, "➕ Homiy kanal username:\nMisol: @kanal_nomi")

    elif call.data == "homiy_ochir":
        homiylar = homiylar_yuklash()
        if not homiylar:
            bot.send_message(call.message.chat.id, "📭 Homiy yo'q.")
            return
        matn = "🤝 Homiylar:\n\n"
        matn += "\n".join(f"{i+1}. {h}" for i, h in enumerate(homiylar))
        matn += "\n\nO'chirish uchun raqamini yozing:"
        set_state(uid, "homiy_ochir")
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "homiy_list":
        homiylar = homiylar_yuklash()
        if not homiylar:
            bot.send_message(call.message.chat.id, "📭 Homiy yo'q.")
            return
        matn = "🤝 Homiylar:\n\n" + "\n".join(f"{i+1}. {h}" for i, h in enumerate(homiylar))
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "admin_qosh":
        if uid != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Faqat bosh admin qo'sha oladi!", show_alert=True)
            return
        set_state(uid, "admin_qosh")
        bot.send_message(call.message.chat.id, "👤 Yangi admin user_id ni yozing:")

    elif call.data == "admin_ochir":
        if uid != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Faqat bosh admin o'chira oladi!", show_alert=True)
            return
        adminlar = list(adminlar_col.find())
        if not adminlar:
            bot.send_message(call.message.chat.id, "📭 Qo'shimcha admin yo'q.")
            return
        matn = "👤 Adminlar:\n\n"
        matn += "\n".join(f"{i+1}. {a['user_id']}" for i, a in enumerate(adminlar))
        matn += "\n\nO'chirish uchun raqamini yozing:"
        set_state(uid, "admin_ochir")
        bot.send_message(call.message.chat.id, matn)

    elif call.data == "admin_list":
        adminlar = list(adminlar_col.find())
        matn = f"👑 Bosh admin: {ADMIN_ID}\n\n"
        if adminlar:
            matn += "👤 Qo'shimcha adminlar:\n"
            matn += "\n".join(f"{i+1}. {a['user_id']}" for i, a in enumerate(adminlar))
        else:
            matn += "Qo'shimcha admin yo'q."
        bot.send_message(call.message.chat.id, matn)

print("✅ Bot ishlamoqda!")
bot.polling(none_stop=True, interval=0, timeout=20)
