import os
import telebot
import openai
from gtts import gTTS

# Токены
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
openai.api_key = OPENAI_KEY

# Режимы работы
mode = "auto"  # по умолчанию auto

# Команды для переключения режима
@bot.message_handler(commands=['teacher_on'])
def set_teacher(message):
    global mode
    mode = "teacher"
    bot.reply_to(message, "🧑‍🏫 Режим учителя: всегда исправляю и объясняю.")

@bot.message_handler(commands=['teacher_off'])
def set_chat(message):
    global mode
    mode = "chat"
    bot.reply_to(message, "💬 Режим собеседника: только общение, без исправлений.")

@bot.message_handler(commands=['mix'])
def set_mix(message):
    global mode
    mode = "mix"
    bot.reply_to(message, "🔀 Режим mix: исправляю только если попросишь.")

@bot.message_handler(commands=['auto'])
def set_auto(message):
    global mode
    mode = "auto"
    bot.reply_to(message, "🤖 Режим auto: исправляю только если есть ошибки. Если задаёшь вопросы про грамматику — объясняю.")

@bot.message_handler(commands=['status'])
def get_status(message):
    bot.reply_to(message, f"Текущий режим: {mode}")

# Функция генерации ответа
def generate_reply(user_text):
    global mode

    if mode == "teacher":
        system = (
            "Ты строгий учитель немецкого языка. "
            "Если ученик пишет по-немецки — сначала коротко ответь на немецком, "
            "потом укажи и объясни все ошибки на русском. "
            "Если ученик задаёт вопрос про грамматику или ошибки — "
            "подробно объясни правило и дай примеры. "
            "После объяснения вернись к обычному режиму учителя."
        )

    elif mode == "auto":
        system = (
            "Ты собеседник и строгий корректор немецкого языка. "
            "1. Если ученик пишет по-немецки — сначала ответь коротко на немецком (1–2 предложения), "
            "потом проверь на ошибки. "
            "Если есть хотя бы одна ошибка (грамматика, порядок слов, лексика) — исправь и объясни на русском. "
            "Если ошибок нет — напиши 'Ошибок нет'. "
            "2. Если ученик задаёт вопрос про грамматику или ошибки — "
            "подробно объясни правило и дай примеры на русском. "
            "3. После объяснения вернись в режим auto."
        )

    elif mode == "chat":
        system = "Ты собеседник. Отвечай только по-немецки, без исправлений."

    elif mode == "mix":
        system = (
            "Ты собеседник. Отвечай на немецком. "
            "Исправляй ошибки только если пользователь прямо попросит ('исправь', 'korrigiere')."
        )

    else:
        system = "Ты собеседник. Отвечай на немецком."

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text}
        ]
    )
    return response.choices[0].message["content"]

# Ответ на текст
@bot.message_handler(content_types=['text'])
def handle_text(message):
    answer = generate_reply(message.text)

    # Отправляем текстовый ответ
    bot.reply_to(message, answer)

    # Генерация голосового ответа (только немецкая часть)
    german_part = answer.split("✍️")[0].strip().split("Ошибок нет")[0].strip()
    if german_part:
        tts = gTTS(text=german_part, lang="de")
        filename = "voice.mp3"
        tts.save(filename)
        with open(filename, "rb") as f:
            bot.send_voice(message.chat.id, f)

print("🤖 Bot läuft...")
bot.polling()
