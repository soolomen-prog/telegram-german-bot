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

# === Per-user режимы ===
# "teacher" | "chat" | "mix"
user_modes = {}  # user_id -> mode
DEFAULT_MODE = "chat"

def get_mode(user_id: int) -> str:
    return user_modes.get(user_id, DEFAULT_MODE)

def set_mode(user_id: int, mode: str):
    user_modes[user_id] = mode

# === TTS (voice & fallback mp3) ===
def send_tts(chat_id: int, text: str, base: str = "reply"):
    """
    1) Пробуем OGG/Opus -> send_voice (кружок)
    2) Если не вышло — MP3 -> send_audio (карточка)
    """
    # --- 1) OGG/Opus ---
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
        print("OGG/Opus TTS failed, fallback to MP3:", e)
        traceback.print_exc()

    # --- 2) MP3 fallback ---
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
    """
    Возвращает (german_reply, ru_explain_or_empty)
    - german_reply: короткий натуральный ответ на немецком
    - ru_explain_or_empty: пусто либо исправления+объяснение на русском
    """
    if mode == "teacher":
        system = (
            "Ты учитель немецкого. Сначала дай короткий естественный ответ на немецком "
            "(1–2 предложения, без перечислений). Затем оцени реплику ученика и подготовь "
            "отдельный краткий блок исправлений на русском: что было неправильно и почему, "
            "с 1–2 примерами. Если ошибок нет — напиши 'Ошибок нет'."
        )
    elif mode == "mix":
        system = (
            "Ты собеседник на немецком. Отвечай коротко и естественно на немецком. "
            "Исправляй и объясняй ошибки только если пользователь явно просит "
            "(по-русски 'исправь', по-немецки 'korrigiere', 'korrigieren', 'Fehler', 'korrektur'). "
            "Если явной просьбы нет — не давай исправлений."
        )
    else:  # chat
        system = (
            "Ты собеседник на немецком. Отвечай естественно и коротко (1–2 предложения). "
            "Не давай исправлений и объяснений."
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

    # Простое разделение на немецкий ответ + русское объяснение.
    # В режиме teacher модель, как правило, выдаст 2 смысловых части.
    german_reply = full
    ru_explain = ""

    # Эвристика: пытаемся отделить русский блок, если он есть.
    # Ищем маркеры кириллицы в конце или абзац с русским текстом.
    if mode in ("teacher", "mix"):
        # если в ответе есть кириллица — отделим последний абзац с кириллицей
        parts = [p.strip() for p in full.split("\n") if p.strip()]
        ru_parts = [p for p in parts if any("а" <= ch <= "я" or "А" <= ch <= "Я" for ch in p)]
        if ru_parts:
            # русский блок — все строки с кириллицей (соединим)
            ru_explain = "\n".join(ru_parts)
            # немецкий — остальное (соединим в 1–2 предложения)
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
        "• /teacher_on – режим Учителя (исправляю и объясняю по-русски)\n"
        "• /teacher_off – режим Собеседника (только по-немецки)\n"
        "• /mix – исправляю только по просьбе\n"
        "• /status – показать текущий режим\n\n"
        "Schick mir Text oder eine Sprachnachricht!"
    )

@bot.message_handler(commands=['teacher_on'])
def teacher_on(message):
    set_mode(message.from_user.id, "teacher")
    bot.send_message(message.chat.id, "🧑‍🏫 Режим Учителя включён: отвечаю по-немецки, ошибки объясняю по-русски.")

@bot.message_handler(commands=['teacher_off'])
def teacher_off(message):
    set_mode(message.from_user.id, "chat")
    bot.send_message(message.chat.id, "💬 Режим Собеседника: только по-немецки, без исправлений.")

@bot.message_handler(commands=['mix'])
def mix_mode(message):
    set_mode(message.from_user.id, "mix")
    bot.send_message(message.chat.id, "🔀 Микс: по-немецки, ошибки исправляю только по просьбе.")

@bot.message_handler(commands=['status'])
def status(message):
    mode = get_mode(message.from_user.id)
    labels = {"teacher": "Учитель", "chat": "Собеседник", "mix": "Микс"}
    bot.send_message(message.chat.id, f"⚙️ Текущий режим: {labels.get(mode, mode)}")

# === Voice ===
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        mode = get_mode(message.from_user.id)

        # скачать OGG от Telegram
        file_info = bot.get_file(message.voice.file_id)
        file = requests.get(f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}', timeout=30)
        local_path = "voice.ogg"
        with open(local_path, "wb") as f:
            f.write(file.content)

        # Распознавание
        with open(local_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )
        user_text = getattr(transcript, "text", str(transcript)).strip()

        # Генерация ответа
        de_answer, ru_explain = generate_reply(user_text, mode)

        # Текстом + голосом
        bot.send_message(message.chat.id, de_answer)
        send_tts(message.chat.id, de_answer, base="voice_reply")

        # Объяснение по-русски (если есть)
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
        bot.send_message(message.chat.id, "Entschuldige, da ist etwas schiefgelaufen. Bitte versuche es später erneut.")
        print("Text handler error:", e)
        traceback.print_exc()

print("🤖 Bot läuft...")
bot.polling(none_stop=True)
