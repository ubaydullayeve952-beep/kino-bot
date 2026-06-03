import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8609768408:AAGOg5DA2xEVpldpx5OZPLx-b6_T4LKtvIs"
ADMIN_ID = 8552250498

bot = telebot.TeleBot(TOKEN)
kinolar = {}
kino_counter = 1

def admin_mi(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=["start"])
def start(message):
    if admin_mi(message.from_user.id):
        admin_panel(message)
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

@bot.message_handler(func=lambda m: m.text.isdigit() and not admin_mi(m.from_user.id))
def kino_yuborish(message):
    raqam = int(message.text.strip())
    if raqam in kinolar:
        kino = kinolar[raqam]
        bot.send_video(message.chat.id, kino['file_id'], caption=f"{kino['nomi']} | {kino['yil']}")
    else:
        bot.send_message(message.chat.id, f"{raqam} raqamli kino topilmadi!")

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
    if not admin_mi(call.from_user.id):
        bot.answer_callback_query(call.id, "Ruxsat yoq!")
        return
    if call.data == "kino_qosh":
        msg = bot.send_message(call.message.chat.id, "Kino nomini yozing:")
        bot.register_next_step_handler(msg, kino_nom_olish)
    elif call.data == "kino_ochir":
        if not kinolar:
            bot.send_message(call.message.chat.id, "Kino yoq.")
            return
        msg = bot.send_message(call.message.chat.id, "Qaysi raqamli kinoni ochirish kerak?")
        bot.register_next_step_handler(msg, kino_ochirish)
    elif call.data == "kino_list":
        if not kinolar:
            bot.send_message(call.message.chat.id, "Kino yoq.")
            return
        matn = "Barcha Kinolar:\n\n"
        for raqam, kino in kinolar.items():
            matn += f"{raqam}. {kino['nomi']} | {kino['yil']}\n"
        bot.send_message(call.message.chat.id, matn)

def kino_nom_olish(message):
    bot.send_message(message.chat.id, "Yilini yozing:")
    bot.register_next_step_handler(message, lambda m: kino_yil_olish(m, message.text))

def kino_yil_olish(message, nomi):
    bot.send_message(message.chat.id, "Endi video faylni yuboring:")
    bot.register_next_step_handler(message, lambda m: kino_video_olish(m, nomi, message.text))

def kino_video_olish(message, nomi, yil):
    global kino_counter
    if message.video:
        file_id = message.video.file_id
        kinolar[kino_counter] = {"nomi": nomi, "yil": yil, "file_id": file_id}
        bot.send_message(message.chat.id, f"Kino qoshildi! Raqam: {kino_counter}\nNomi: {nomi}")
        kino_counter += 1
    else:
        bot.send_message(message.chat.id, "Video yuboring!")

def kino_ochirish(message):
    try:
        raqam = int(message.text.strip())
        if raqam in kinolar:
            nomi = kinolar[raqam]["nomi"]
            del kinolar[raqam]
            bot.send_message(message.chat.id, f"{nomi} ochirildi!")
        else:
            bot.send_message(message.chat.id, f"{raqam} raqamli kino topilmadi!")
    except:
        bot.send_message(message.chat.id, "Raqam kiriting!")

print("Bot ishlamoqda...")
bot.polling(none_stop=True)
