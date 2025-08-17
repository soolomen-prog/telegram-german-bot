import os
import traceback
import requests
import telebot
from datetime import datetime
from openai import OpenAI

# === Env ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in environment variables")

# === Clients ===
bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# === Режимы ===
# "teacher" | "chat" | "mix" | "auto"
user_modes = {}
DEFAULT_MODE = "chat"

def get_mode(user_id: int) -> str:
    return user_modes.get(user_id, DEFAULT_MODE)

def set_mode(user_id: int, mode: str):
    user_modes[user_id] = mode

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

# === Генерация ответа ===
def generate_reply(user_text: str, mode: str):
    if mode == "teacher":
        system = (
            "Ты учитель немецкого. Сначала дай короткий естественный ответ на немецком "
            "для продолжения разговора. Затем оцени реплику ученика и подготовь "
            "отдельный краткий блок исправлений на русском. Если ошибок нет — напиши 'Ошибок нет'."
        )
    elif mode == "mix":
        system = (
            "Ты собеседник на немецком. Отвечай коротко и естественно. "
            "Исправляй ошибки только если пользователь явно просит ('исправь', 'korrigiere')."
        )
    elif mode == "auto":
        system = (
           "Ты собеседник и строгий корректор немецкого языка. "
            "1. Сначала дай короткий естественный ответ на немецком (1–2 предложения), продолжая разговор. "
            "2. Потом проверь сообщение ученика на грамматические, синтаксические и лексические ошибки. "
            "3. Если есть хотя бы одна ошибка (включая порядок слов!) — напиши исправленное предложение и объясни на русском. "
            "4. Если ошибок нет — напиши 'Ошибок нет'."
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

    if mode in ("teacher", "auto"):
        parts = [p.strip() for p in full.split("\n") if p.strip()]
        ru_parts = [p for p in parts if any("а" <= ch <= "я" or "А" <= ch <= "Я" for ch in p)]
        if ru_parts:
            ru_explain = "\n".join(ru_parts)
            de_parts = [p for p in parts if p not in ru_parts]
            german_reply = " ".join(de_parts).strip() or german_reply

    return german_reply, ru_explain

# === Команды ===
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
        "• /status – показать текущий режим\n\n"
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

    except Exception as e:
        bot.send_message(message.chat.id, "Entschuldige, da ist etwas schiefgelaufen.")
        print("Text handler error:", e)
        traceback.print_exc()

print("🤖 Bot läuft...")
bot.polling(none_stop=True)
