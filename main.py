import os
import traceback
import requests
import telebot
from telebot import types
from datetime import datetime
from openai import OpenAI

# === Env ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in environment variables")

# === Donate ===
DONATE_URL = "https://buymeacoffee.com/debot"  # твоя ссылка на поддержку
DONATE_REMINDER_EVERY = 15                      # напоминать каждые N сообщений (можно изменить)
user_msg_count = {}                              # user_id -> int

# === Clients ===
bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# === Режимы ===
# "teacher" | "chat" | "mix" | "auto"
user_modes = {}
DEFAULT_MODE = "teacher"   # <-- по умолчанию теперь Учитель

def get_mode(user_id: int) -> str:
    return user_modes.get(user_id, DEFAULT_MODE)

def set_mode(user_id: int, mode: str):
    user_modes[user_id] = mode

# === Напоминание о донате ===
def send_donate_message(chat_id: int, short: bool = False):
    text_long = (
        "💬 Этот бот помогает практиковать немецкий. "
        "Если он тебе полезен — можно поддержать проект ☕\n"
        "Любая поддержка помогает развивать новые функции и держать бота живым ❤️"
    )
    text_short = "☕ Нравится бот? Можно поддержать проект — это очень помогает 💛"
    text = text_short if short else text_long

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("☕ Поддержать проект", url=DONATE_URL))
    bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)

def inc_and_maybe_remind(chat_id: int, user_id: int):
    cnt = user_msg_count.get(user_id, 0) + 1
    user_msg_count[user_id] = cnt
    if DONATE_REMINDER_EVERY and cnt % DONATE_REMINDER_EVERY == 0:
        send_donate_message(chat_id, short=True)

# === TTS (OGG + fallback MP3) ===
def send_tts(chat_id: int, text: str, base: str = "reply"):
    try:
        ogg_path = f"{base}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.ogg"
        with client.audio.speech.with_streaming_response.create(
            model="tts-1",
            voice="alloy",
            input=text,
            response_format="opus"
        ) as resp:
            resp.stream_to_file(ogg_path)
        with open(ogg_path, "rb") as f:
            bot.send_voice(chat_id, f)
        return
    except Exception as e:
        print("OGG/Opus TTS failed:", e)
        traceback.print_exc()

    try:
        mp3_path = f"{base}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.mp3"
        with client.audio.speech.with_streaming_response.create(
            model="tts-1",
            voice="alloy",
            input=text,
            response_format="mp3"
        ) as resp:
            resp.stream_to_file(mp3_path)
        with open(mp3_path, "rb") as f:
            bot.send_audio(chat_id, f, title="Antwort (TTS)")
    except Exception as e2:
        print("MP3 TTS also failed:", e2)
        traceback.print_exc()

# === Детектор "как сказать" ===
def detect_translation_request(user_text: str) -> bool:
    triggers = [
        "как сказать", "как будет по-немецки", "не знаю как сказать", "переведи",
        "wie sagt man", "how to say", "translate"
    ]
    if any(t in user_text.lower() for t in triggers):
        return True

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Определи: похоже ли сообщение на запрос перевода или поиск слова? Ответь только 'Да' или 'Нет'."},
                {"role": "user", "content": user_text}
            ],
            temperature=0
        )
        answer = resp.choices[0].message.content.strip().lower()
        return "да" in answer
    except:
        return False

# === Генерация ответа ===
def generate_reply(user_text: str, mode: str):
    if detect_translation_request(user_text):
        system = (
            "Пользователь ищет перевод или не знает, как сказать что-то по-немецки. "
            "Дай перевод, объясни грамматику и построй 2–3 примера. "
            "Пиши на русском объяснение, примеры на немецком."
        )
    elif mode == "teacher":
        system = (
            "Ты учитель немецкого языка. Отвечай на немецком (1–2 предложения), "
            "чтобы продолжить диалог. Затем, отдельно, сделай блок: "
            "'Исправления:' с объяснением ошибок на русском. "
            "Если ошибок нет — напиши 'Ошибок нет'."
        )
    elif mode == "mix":
        system = (
            "Ты собеседник на немецком. Отвечай коротко и естественно. "
            "Исправляй ошибки только если пользователь явно просит ('исправь', 'korrigiere')."
        )
    elif mode == "auto":
        system = (
            "Ты собеседник на немецком. Отвечай естественно и коротко (1–2 предложения). "
            "Если в сообщении ученика есть ошибки — добавь отдельный блок 'Исправления:' "
            "с объяснением ошибок на русском. "
            "Если ошибок нет — просто ответь по-немецки."
        )
    else:  # chat
        system = (
            "Ты собеседник на немецком. Отвечай естественно и коротко. "
            "Не исправляй и не объясняй."
        )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text}
        ],
        temperature=0.7,
    )
    full = resp.choices[0].message.content.strip()

    german_reply = full
    ru_explain = ""

    if "Исправления:" in full:
        parts = full.split("Исправления:")
        german_reply = parts[0].strip()
        ru_explain = "Исправления:" + parts[1].strip()

    return german_reply, ru_explain

# === Команды ===
@bot.message_handler(commands=['donate'])
def donate_cmd(message):
    send_donate_message(message.chat.id, short=False)

@bot.message_handler(commands=['start', 'help'])
def start(message):
    set_mode(message.from_user.id, DEFAULT_MODE)
    bot.send_message(
        message.chat.id,
        "👋 Hallo! Ich bin dein Deutsch-Bot.\n"
        "Команды:\n"
        "• /teacher_on – всегда исправляю и объясняю\n"
        "• /teacher_off – только немецкий, без исправлений\n"
        "• /mix – исправляю только по просьбе\n"
        "• /auto – исправляю автоматически, но только если ошибки есть\n"
        "• /status – показать текущий режим\n"
        "• /lesson – начать урок\n"
        "• /donate – поддержать проект ☕\n\n"
        "Schick mir Text oder eine Sprachnachricht!"
    )

@bot.message_handler(commands=['teacher_on'])
def teacher_on(message):
    set_mode(message.from_user.id, "teacher")
    bot.send_message(message.chat.id, "🧑‍🏫 Режим Учителя включён.")

@bot.message_handler(commands=['teacher_off'])
def teacher_off(message):
    set_mode(message.from_user.id, "chat")
    bot.send_message(message.chat.id, "💬 Режим Собеседника включён.")

@bot.message_handler(commands=['mix'])
def mix_mode(message):
    set_mode(message.from_user.id, "mix")
    bot.send_message(message.chat.id, "🔀 Микс включён.")

@bot.message_handler(commands=['auto'])
def auto_mode(message):
    set_mode(message.from_user.id, "auto")
    bot.send_message(message.chat.id, "🤖 Авто-режим: исправляю только если ошибки есть.")

@bot.message_handler(commands=['status'])
def status(message):
    mode = get_mode(message.from_user.id)
    labels = {"teacher": "Учитель", "chat": "Собеседник", "mix": "Микс", "auto": "Авто"}
    bot.send_message(message.chat.id, f"⚙️ Текущий режим: {labels.get(mode, mode)}")

# === Уроки ===
@bot.message_handler(commands=['lesson'])
def lesson(message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Приветствие", callback_data="lesson_greeting"))
    keyboard.add(types.InlineKeyboardButton("Покупки", callback_data="lesson_shopping"))
    keyboard.add(types.InlineKeyboardButton("Путешествия", callback_data="lesson_travel"))
    keyboard.add(types.InlineKeyboardButton("Работа", callback_data="lesson_work"))
    bot.send_message(message.chat.id, "📚 Выбери тему урока:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("lesson_"))
def lesson_callback(call):
    topic = call.data.split("_", 1)[1]
    system = (
        f"Сделай мини-урок по теме '{topic}'. "
        "1) Объясни правило/фразы (на русском), "
        "2) дай 2–3 примера на немецком, "
        "3) задай вопрос пользователю для практики."
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system}],
        temperature=0.7,
    )
    lesson_text = resp.choices[0].message.content.strip()
    bot.send_message(call.message.chat.id, lesson_text)

# === Voice ===
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        mode = get_mode(message.from_user.id)

        file_info = bot.get_file(message.voice.file_id)
        file = requests.get(f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}', timeout=30)
        local_path = "voice.ogg"
        with open(local_path, "wb") as f:
            f.write(file.content)

        with open(local_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )
        user_text = getattr(transcript, "text", str(transcript)).strip()

        de_answer, ru_explain = generate_reply(user_text, mode)

        bot.send_message(message.chat.id, de_answer)
        send_tts(message.chat.id, de_answer, base="voice_reply")

        if ru_explain:
            bot.send_message(message.chat.id, f"✍️ {ru_explain}")

        inc_and_maybe_remind(message.chat.id, message.from_user.id)

    except Exception as e:
        bot.send_message(message.chat.id, "Es gab einen Fehler. Versuche es bitte noch einmal.")
        print("Voice handler error:", e)
        traceback.print_exc()

# === Text ===
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    try:
        mode = get_mode(message.from_user.id)
        de_answer, ru_explain = generate_reply(message.text, mode)

        bot.send_message(message.chat.id, de_answer)
        send_tts(message.chat.id, de_answer, base="text_reply")

        if ru_explain:
            bot.send_message(message.chat.id, f"✍️ {ru_explain}")

        inc_and_maybe_remind(message.chat.id, message.from_user.id)

    except Exception as e:
        bot.send_message(message.chat.id, "Entschuldige, da ist etwas schiefgelaufen.")
        print("Text handler error:", e)
        traceback.print_exc()

print("🤖 Bot läuft...")
bot.polling(none_stop=True)
