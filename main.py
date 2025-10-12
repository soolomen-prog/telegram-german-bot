import os
import traceback
import requests
import telebot
from telebot import types
from datetime import datetime, timezone
from openai import OpenAI
from collections import defaultdict

# === Env ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Telegram ID администратора (для /stats)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in environment variables")

# === Donate ===
DONATE_URL = "https://buymeacoffee.com/debot"  # ссылка на поддержку
DONATE_REMINDER_EVERY = 15                      # напоминать каждые N сообщений (0 = выкл)
user_msg_count = {}                              # user_id -> int

# === Clients ===
bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# === Режимы ===
# "teacher" | "chat" | "mix" | "auto"
user_modes = {}
DEFAULT_MODE = "teacher"   # по умолчанию Учитель

def get_mode(user_id: int) -> str:
    return user_modes.get(user_id, DEFAULT_MODE)

def set_mode(user_id: int, mode: str):
    user_modes[user_id] = mode

# === Простая аналитика ===
def utcnow():
    return datetime.now(timezone.utc)

def ymd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

# Пер-пользовательская статистика
user_stats = {}  # user_id -> {"total":int, "text":int, "voice":int, "first":dt, "last":dt}

# Дневные агрегаты
daily_messages = defaultdict(int)     # "YYYY-MM-DD" -> count
daily_unique = defaultdict(set)       # "YYYY-MM-DD" -> {user_id}

def bump_stats(user_id: int, kind: str):
    """
    kind: 'text' | 'voice'
    """
    now = utcnow()
    d = ymd(now)

    st = user_stats.get(user_id)
    if not st:
        st = {"total": 0, "text": 0, "voice": 0, "first": now, "last": now}
        user_stats[user_id] = st

    st["total"] += 1
    st[kind] += 1
    st["last"] = now

    daily_messages[d] += 1
    daily_unique[d].add(user_id)

def format_admin_stats(days: int = 7) -> str:
    # Общие итоги
    total_users = len(user_stats)
    total_msgs = sum(s["total"] for s in user_stats.values())
    text_msgs = sum(s["text"] for s in user_stats.values())
    voice_msgs = sum(s["voice"] for s in user_stats.values())

    # Последние N дней
    lines = []
    today = utcnow().date()
    for i in range(days):
        day = today.fromordinal(today.toordinal() - i)
        key = day.strftime("%Y-%m-%d")
        msgs = daily_messages.get(key, 0)
        uniq = len(daily_unique.get(key, set()))
        lines.append(f"{key}: {msgs} сообщений, {uniq} пользователей")

    lines = "\n".join(lines)

    return (
        "📈 Статистика бота\n"
        f"• Пользователей всего: {total_users}\n"
        f"• Сообщений всего: {total_msgs} (текст: {text_msgs}, голос: {voice_msgs})\n\n"
        f"🗓 За последние {days} дн.:\n{lines}"
    )

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

# === Команды утилиты/донат ===
@bot.message_handler(commands=['donate'])
def donate_cmd(message):
    send_donate_message(message.chat.id, short=False)

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, format_admin_stats(7))
    else:
        bot.send_message(message.chat.id, "Команда доступна только администратору.")

# === Команды режима/старт ===
@bot.message_handler(commands=['start', 'help'])
def start(message):
    set_mode(message.from_user.id, DEFAULT_MODE)
    # зарегистрируем визит в статистике (без увеличения счетчиков сообщений)
    if message.from_user.id not in user_stats:
        user_stats[message.from_user.id] = {"total": 0, "text": 0, "voice": 0, "first": utcnow(), "last": utcnow()}

    bot.send_message(
        message.chat.id,
        "👋 Привет! Я твой Deutsch-бот.\n"
        "Команды:\n"
        "• /teacher_on – всегда исправляю и объясняю\n"
        "• /teacher_off – только немецкий, без исправлений\n"
        "• /mix – исправляю только по просьбе\n"
        "• /auto – исправляю автоматически, но только если ошибки есть\n"
        "• /status – показать текущий режим\n"
        "• /donate – поддержать проект ☕\n"
        "• /stats – статистика бота (админ)\n\n"
        "Отправь текст или голосовое сообщение!"
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
        bump_stats(message.from_user.id, "voice")
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
            bot.send_message(message.chat.id, f"✍️ {ру_explain}")

        inc_and_maybe_remind(message.chat.id, message.from_user.id)

    except Exception as e:
        bot.send_message(message.chat.id, "Es gab einen Fehler. Versuche es bitte noch einmal.")
        print("Voice handler error:", e)
        traceback.print_exc()

# === Text ===
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    try:
        bump_stats(message.from_user.id, "text")
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
