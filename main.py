import telebot
import json
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8609768408:AAGOg5DA2xEVpldpx5OZPLx-b6_T4LKtvIs"
ADMIN_ID = 8552250498

HOMIYLAR = [
    "@uzbekcha_kinolarmi",
]

KANAL = "https://@uzbekcha_kinolarmi"

bot = telebot.TeleBot(TOKEN)
FAYL = "kinolar.json"

def kinolar_yuklash():
    if os.path.exists(FAYL):
        with open(FAYL, "r") as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    return {}

def kinolar_saqlash(kinolar):
    with open(FAYL, "w") as f:
        json.dump(kinolar, f)

kinolar = kinolar_yuklash()

def admin_mi(user_id):
    return user_id == ADMIN_ID

def obuna_tekshir(user_id):
    for kanal in HOMIYLAR:
        try:
            member = bot.get_chat_member(kanal, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

def obuna_tugmalari():
    tugmalar = InlineKeyboardMarkup()
    for kanal in HOMIYLAR:
        tugmalar.add(InlineKeyboardButton(f"Obuna bolish {kanal}", url=f"https://t.me/{kanal[1:]}"))
    tugmalar.add(InlineKeyboardButton("Tekshirish ✅", callback_data="tekshir"))
    return tugmalar

@bot.message_handler(commands=["start"])
def start(message):
    if admin_mi(message.from_user.id):
        admin_panel(message)
        return
    if HOMIYLAR and not obuna_tekshir(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Botdan foydalanish uchun quyidagi kanallarga obuna boling!",
            reply_markup=obuna_tugmalari()
        )
        return
    bot.send_message(message.chat.id, "Kino Botga Xush Kelibsiz!\nKino raqamini yuboring!\n/kinolar royxat")

@bot.message_handler(commands=["kinolar"])
def kinolar_royxati(message):
    if not kinolar:
        bot.send_message(message.chat.id, "Hozircha kino yoq.")
        return
    matn = "Mavjud Kinolar:\n\n"
    for raqam, kino in kinolar.items():
        matn += f"{raqam}. {kino['nomi']}\n"
    matn += "\nRaqam yuboring!"
    bot.send_message(message.chat.id, matn)

@bot.message_handler(func=lambda m: m.text and m.text.isdigit() and not admin_mi(m.from_user.id))
def kino_yuborish(message):
    if HOMIYLAR and not obuna_tekshir(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Botdan foydalanish uchun quyidagi kanallarga obuna boling!",
            reply_markup=obuna_tugmalari()
        )
        return
    raqam = int(message.text.strip())
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
            f"{raqam} raqamli kino topilmadi!\n\n🎬 Barcha kinolar: {KANAL}"
        )

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if not admin_mi(message.from_user.id):
        bot.send_message(message.chat.id, "Ruxsat yoq!")
        return
    tugmalar = InlineKeyboardMarkup()
    tugmalar.add(InlineKeyboardButton("Kino Qoshish", callback_data="kino_qosh"))
    tugmalar.add(InlineKeyboardButton("Kino Ochirish", callback_data="kino_ochir"))
    tugmalar.add(InlineKeyboardButton("Barcha Kinolar", callback_data="kino_list"))
    bot.send_message(message.chat.id, "Admin Panel", reply_markup=tugmalar)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "tekshir":
        if obuna_tekshir(call.from_user.id):
            bot.send_message(call.message.chat.id, "Rahmat! Endi botdan foydalanishingiz mumkin!")
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
        if not kinolar:
            bot.send_message(call.message.chat.id, "Kino yoq.")
            return
        msg = bot.send_message(call.message.chat.id, "Qaysi raqamni ochirish kerak?")
        bot.register_next_step_handler(msg, kino_ochirish)
    elif call.data == "kino_list":
        if not kinolar:
            bot.send_message(call.message.chat.id, "Kino yoq.")
            return
        matn = "Barcha Kinolar:\n\n"
        for raqam, kino in kinolar.items():
            matn += f"{raqam}. {kino['nomi']}\n"
        bot.send_message(call.message.chat.id, matn)

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
        kinolar[raqam] = {"nomi": nomi, "file_id": file_id, "tip": tip}
        kinolar_saqlash(kinolar)
        bot.send_message(message.chat.id, f"Kino qoshildi!\nRaqam: {raqam}\nNomi: {nomi}")
    else:
        bot.send_message(message.chat.id, f"Xato! Tur: {message.content_type}\nQaytadan yuboring!")

def kino_ochirish(message):
    global kinolar
    try:
        raqam = int(message.text.strip())
        if raqam in kinolar:
            nomi = kinolar[raqam]["nomi"]
            del kinolar[raqam]
            kinolar_saqlash(kinolar)
            bot.send_message(message.chat.id, f"{nomi} ochirildi!")
        else:
            bot.send_message(message.chat.id, f"{raqam} raqamli kino topilmadi!")
    except:
        bot.send_message(message.chat.id, "Raqam kiriting!")

print("Bot ishlamoqda...")
bot.polling(none_stop=True)
