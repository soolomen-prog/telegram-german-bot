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
DONATE_URL = "https://buymeacoffee.com/debot"
DONATE_REMINDER_EVERY = 15
user_msg_count = {}

# === Clients ===
bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# === Режимы ===
# "teacher" | "chat" | "mix" | "auto"
user_modes = {}
DEFAULT_MODE = "teacher"

def get_mode(user_id: int) -> str:
    return user_modes.get(user_id, DEFAULT_MODE)

def set_mode(user_id: int, mode: str):
    user_modes[user_id] = mode

# === Языки UI ===
LANGS = ["ru", "uk", "en", "tr", "fa", "ar"]
LANG_TITLES = {
    "ru": "Русский",
    "uk": "Українська",
    "en": "English",
    "tr": "Türkçe",
    "fa": "فارسی",
    "ar": "العربية",
}
user_langs = {}
DEFAULT_LANG = "en"  # приветствие и первый экран на английском

def get_lang(user_id: int) -> str:
    return user_langs.get(user_id, DEFAULT_LANG)

def set_lang(user_id: int, lang: str):
    if lang in LANGS:
        user_langs[user_id] = lang

# Локализация строк
I18N = {
    "ru": {
        "greet": "👋 Привет! Я твой Deutsch-бот.\nВыбери язык интерфейса:",
        "help": (
            "Команды:\n"
            "• /teacher_on — всегда исправляю и объясняю\n"
            "• /teacher_off — только немецкий, без исправлений\n"
            "• /mix — исправляю только по просьбе\n"
            "• /auto — исправляю автоматически, но только если ошибки есть\n"
            "• /status — показать текущий режим\n"
            "• /language — сменить язык интерфейса\n"
            "• /donate — поддержать проект ☕\n"
            "• /stats — статистика бота (админ)\n\n"
            "Отправь текст или голосовое сообщение!"
        ),
        "mode_teacher_on": "🧑‍🏫 Режим Учителя включён.",
        "mode_chat_on": "💬 Режим Собеседника включён.",
        "mode_mix_on": "🔀 Микс включён.",
        "mode_auto_on": "🤖 Авто-режим: исправляю только если ошибки есть.",
        "status": "⚙️ Текущий режим: {mode}",
        "modes_labels": {"teacher": "Учитель", "chat": "Собеседник", "mix": "Микс", "auto": "Авто"},
        "donate_long": (
            "💬 Этот бот помогает практиковать немецкий.\n"
            "Если он тебе полезен — можно поддержать проект ☕\n"
            "Любая поддержка помогает развивать новые функции и держать бота живым ❤️"
        ),
        "donate_short": "☕ Нравится бот? Можно поддержать проект — это очень помогает 💛",
        "donate_btn": "☕ Поддержать проект",
        "admin_only": "Команда доступна только администратору.",
        "err_voice": "Произошла ошибка. Попробуй ещё раз.",
        "err_text": "Извини, что-то пошло не так.",
        "lang_choose": "🌐 Выбери язык интерфейса:",
        "lang_set": "✅ Язык интерфейса: {lang}",
        "corrections": "Исправления:",
        "no_errors": "Ошибок нет",
    },
    "uk": {
        "greet": "👋 Привіт! Я твій Deutsch-бот.\nОберіть мову інтерфейсу:",
        "help": (
            "Команди:\n"
            "• /teacher_on — завжди виправляю та пояснюю\n"
            "• /teacher_off — лише німецькою, без виправлень\n"
            "• /mix — виправляю лише на прохання\n"
            "• /auto — виправляю автоматично, якщо є помилки\n"
            "• /status — показати поточний режим\n"
            "• /language — змінити мову інтерфейсу\n"
            "• /donate — підтримати проєкт ☕\n"
            "• /stats — статистика бота (адмін)\n\n"
            "Надішли текст або голосове повідомлення!"
        ),
        "mode_teacher_on": "🧑‍🏫 Режим Вчителя увімкнено.",
        "mode_chat_on": "💬 Режим Співрозмовника увімкнено.",
        "mode_mix_on": "🔀 Мікс увімкнено.",
        "mode_auto_on": "🤖 Авто-режим: виправляю лише якщо є помилки.",
        "status": "⚙️ Поточний режим: {mode}",
        "modes_labels": {"teacher": "Вчитель", "chat": "Співрозмовник", "mix": "Мікс", "auto": "Авто"},
        "donate_long": (
            "💬 Цей бот допомагає практикувати німецьку.\n"
            "Якщо він корисний — можна підтримати проєкт ☕\n"
            "Будь-яка підтримка допомагає розвивати нові функції ❤️"
        ),
        "donate_short": "☕ Подобається бот? Можна підтримати — це дуже допомагає 💛",
        "donate_btn": "☕ Підтримати проєкт",
        "admin_only": "Команда доступна лише адміністратору.",
        "err_voice": "Сталася помилка. Спробуй ще раз.",
        "err_text": "Вибач, щось пішло не так.",
        "lang_choose": "🌐 Оберіть мову інтерфейсу:",
        "lang_set": "✅ Мову встановлено: {lang}",
        "corrections": "Виправлення:",
        "no_errors": "Помилок немає",
    },
    "en": {
        "greet": "👋 Hi! I’m your Deutsch-bot.\nPlease choose your interface language:",
        "help": (
            "Commands:\n"
            "• /teacher_on — always correct and explain\n"
            "• /teacher_off — German only, no corrections\n"
            "• /mix — correct only on request\n"
            "• /auto — correct automatically if there are mistakes\n"
            "• /status — show current mode\n"
            "• /language — change interface language\n"
            "• /donate — support the project ☕\n"
            "• /stats — bot stats (admin)\n\n"
            "Send me a text or a voice message!"
        ),
        "mode_teacher_on": "🧑‍🏫 Teacher mode enabled.",
        "mode_chat_on": "💬 Chat mode enabled.",
        "mode_mix_on": "🔀 Mix mode enabled.",
        "mode_auto_on": "🤖 Auto mode: I correct only if there are mistakes.",
        "status": "⚙️ Current mode: {mode}",
        "modes_labels": {"teacher": "Teacher", "chat": "Chat", "mix": "Mix", "auto": "Auto"},
        "donate_long": (
            "💬 This bot helps you practice German.\n"
            "If you find it useful, you can support the project ☕\n"
            "Any support helps develop new features ❤️"
        ),
        "donate_short": "☕ Enjoying the bot? You can support the project — it really helps 💛",
        "donate_btn": "☕ Support the project",
        "admin_only": "This command is available to the administrator only.",
        "err_voice": "An error occurred. Please try again.",
        "err_text": "Sorry, something went wrong.",
        "lang_choose": "🌐 Choose your interface language:",
        "lang_set": "✅ Interface language: {lang}",
        "corrections": "Corrections:",
        "no_errors": "No mistakes",
    },
    "tr": {
        "greet": "👋 Merhaba! Ben Deutsch-bot.\nLütfen arayüz dilini seç:",
        "help": (
            "Komutlar:\n"
            "• /teacher_on — her zaman düzeltir ve açıklarım\n"
            "• /teacher_off — sadece Almanca, düzeltme yok\n"
            "• /mix — sadece istek üzerine düzeltirim\n"
            "• /auto — hata varsa otomatik düzeltirim\n"
            "• /status — mevcut modu göster\n"
            "• /language — arayüz dilini değiştir\n"
            "• /donate — projeyi destekle ☕\n"
            "• /stats — bot istatistikleri (admin)\n\n"
            "Metin ya da sesli mesaj gönder!"
        ),
        "mode_teacher_on": "🧑‍🏫 Öğretmen modu etkin.",
        "mode_chat_on": "💬 Sohbet modu etkin.",
        "mode_mix_on": "🔀 Karışık mod etkin.",
        "mode_auto_on": "🤖 Otomatik mod: Sadece hata varsa düzeltirim.",
        "status": "⚙️ Mevcut mod: {mode}",
        "modes_labels": {"teacher": "Öğretmen", "chat": "Sohbet", "mix": "Karışık", "auto": "Otomatik"},
        "donate_long": (
            "💬 Bu bot Almanca pratiği yapmana yardımcı olur.\n"
            "Faydalı bulduysan projeyi destekleyebilirsin ☕\n"
            "Her destek yeni özelliklere yardımcı olur ❤️"
        ),
        "donate_short": "☕ Botu beğendin mi? Destek olabilirsin — çok yardımcı olur 💛",
        "donate_btn": "☕ Projeyi destekle",
        "admin_only": "Bu komut yalnızca yöneticiye özeldir.",
        "err_voice": "Bir hata oluştu. Lütfen tekrar dene.",
        "err_text": "Üzgünüm, bir şeyler ters gitti.",
        "lang_choose": "🌐 Arayüz dilini seç:",
        "lang_set": "✅ Arayüz dili: {lang}",
        "corrections": "Düzeltmeler:",
        "no_errors": "Hata yok",
    },
    "fa": {
        "greet": "👋 سلام! من ربات آلمانی تو هستم.\nلطفاً زبان رابط را انتخاب کن:",
        "help": (
            "دستورات:\n"
            "• /teacher_on — همیشه تصحیح و توضیح می‌دهم\n"
            "• /teacher_off — فقط آلمانی، بدون تصحیح\n"
            "• /mix — فقط در صورت درخواست تصحیح می‌کنم\n"
            "• /auto — اگر خطا باشد خودکار تصحیح می‌کنم\n"
            "• /status — نمایش حالت فعلی\n"
            "• /language — تغییر زبان رابط\n"
            "• /donate — حمایت از پروژه ☕\n"
            "• /stats — آمار بات (ادمین)\n\n"
            "یک پیام متنی یا صوتی بفرست!"
        ),
        "mode_teacher_on": "🧑‍🏫 حالت معلم فعال شد.",
        "mode_chat_on": "💬 حالت گفتگو فعال شد.",
        "mode_mix_on": "🔀 حالت ترکیبی فعال شد.",
        "mode_auto_on": "🤖 حالت خودکار: فقط در صورت وجود خطا تصحیح می‌کنم.",
        "status": "⚙️ حالت فعلی: {mode}",
        "modes_labels": {"teacher": "معلم", "chat": "گفتگو", "mix": "ترکیبی", "auto": "خودکار"},
        "donate_long": (
            "💬 این بات به تمرین آلمانی کمک می‌کند.\n"
            "اگر مفید است می‌توانی از پروژه حمایت کنی ☕\n"
            "هر حمایتی به توسعه ویژگی‌های جدید کمک می‌کند ❤️"
        ),
        "donate_short": "☕ از بات راضی هستی؟ می‌توانی حمایت کنی — خیلی کمک می‌کند 💛",
        "donate_btn": "☕ حمایت از پروژه",
        "admin_only": "این دستور فقط برای ادمین در دسترس است.",
        "err_voice": "خطا رخ داد. دوباره تلاش کن.",
        "err_text": "متأسفم، مشکلی پیش آمد.",
        "lang_choose": "🌐 زبان رابط را انتخاب کن:",
        "lang_set": "✅ زبان رابط: {lang}",
        "corrections": "اصلاحات:",
        "no_errors": "بدون خطا",
    },
    "ar": {
        "greet": "👋 أهلاً! أنا بوت الألمانية.\nيرجى اختيار لغة الواجهة:",
        "help": (
            "الأوامر:\n"
            "• /teacher_on — أصحح وأشرح دائماً\n"
            "• /teacher_off — ألمانية فقط، بلا تصحيح\n"
            "• /mix — أصحح عند الطلب فقط\n"
            "• /auto — أصحح تلقائياً عند وجود أخطاء\n"
            "• /status — عرض الوضع الحالي\n"
            "• /language — تغيير لغة الواجهة\n"
            "• /donate — دعم المشروع ☕\n"
            "• /stats — إحصاءات البوت (المشرف)\n\n"
            "أرسل رسالة نصية أو صوتية!"
        ),
        "mode_teacher_on": "🧑‍🏫 تم تفعيل وضع المعلم.",
        "mode_chat_on": "💬 تم تفعيل وضع الدردشة.",
        "mode_mix_on": "🔀 تم تفعيل الوضع المختلط.",
        "mode_auto_on": "🤖 وضع تلقائي: أصحح فقط عند وجود أخطاء.",
        "status": "⚙️ الوضع الحالي: {mode}",
        "modes_labels": {"teacher": "معلم", "chat": "دردشة", "mix": "مختلط", "auto": "تلقائي"},
        "donate_long": (
            "💬 هذا البوت يساعدك على ممارسة الألمانية.\n"
            "إذا كان مفيداً يمكنك دعم المشروع ☕\n"
            "أي دعم يساعد على تطوير ميزات جديدة ❤️"
        ),
        "donate_short": "☕ هل أعجبك البوت؟ يمكنك دعم المشروع — هذا يساعد كثيراً 💛",
        "donate_btn": "☕ دعم المشروع",
        "admin_only": "هذا الأمر متاح للمشرف فقط.",
        "err_voice": "حدث خطأ. حاول مرة أخرى.",
        "err_text": "عذراً، حدث خطأ ما.",
        "lang_choose": "🌐 اختر لغة الواجهة:",
        "lang_set": "✅ لغة الواجهة: {lang}",
        "corrections": "التصحيحات:",
        "no_errors": "لا توجد أخطاء",
    },
}

def t(lang: str, key: str) -> str:
    return I18N.get(lang, I18N[DEFAULT_LANG]).get(key, key)

# === Простая аналитика ===
def utcnow():
    return datetime.now(timezone.utc)

def ymd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

user_stats = {}  # user_id -> dict
daily_messages = defaultdict(int)
daily_unique = defaultdict(set)

def bump_stats(user_id: int, kind: str):
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
    total_users = len(user_stats)
    total_msgs = sum(s["total"] for s in user_stats.values())
    text_msgs = sum(s["text"] for s in user_stats.values())
    voice_msgs = sum(s["voice"] for s in user_stats.values())

    lines = []
    today = utcnow().date()
    for i in range(days):
        day = today.fromordinal(today.toordinal() - i)
        key = day.strftime("%Y-%m-%d")
        msgs = daily_messages.get(key, 0)
        uniq = len(daily_unique.get(key, set()))
        lines.append(f"{key}: {msgs} msgs, {uniq} users")
    lines = "\n".join(lines)

    return (
        "📈 Bot stats\n"
        f"• Users total: {total_users}\n"
        f"• Messages total: {total_msgs} (text: {text_msgs}, voice: {voice_msgs})\n\n"
        f"🗓 Last {days} days:\n{lines}"
    )

# === Donate helpers ===
def send_donate_message(chat_id: int, lang: str, short: bool = False):
    text = t(lang, "donate_short") if short else t(lang, "donate_long")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(t(lang, "donate_btn"), url=DONATE_URL))
    bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)

def inc_and_maybe_remind(chat_id: int, user_id: int):
    cnt = user_msg_count.get(user_id, 0) + 1
    user_msg_count[user_id] = cnt
    if DONATE_REMINDER_EVERY and cnt % DONATE_REMINDER_EVERY == 0:
        send_donate_message(chat_id, get_lang(user_id), short=True)

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
    except Exception:
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
    except Exception:
        traceback.print_exc()

# === Детектор "как сказать" ===
def detect_translation_request(user_text: str) -> bool:
    triggers = [
        "как сказать", "как будет по-немецки", "не знаю как сказать", "переведи",
        "wie sagt man", "how to say", "translate"
    ]
    if any(tk in user_text.lower() for tk in triggers):
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
        return "да" in answer or "yes" in answer
    except Exception:
        return False

# === Генерация ответа ===
def generate_reply(user_text: str, mode: str, lang: str):
    expl_map = {
        "ru": "на русском",
        "uk": "українською",
        "en": "in English",
        "tr": "Türkçe",
        "fa": "به فارسی",
        "ar": "بالعربية",
    }
    expl_lang = expl_map.get(lang, "in English")
    corrections_tag = t(lang, "corrections")
    no_errors = t(lang, "no_errors")

    if detect_translation_request(user_text):
        system = (
            "Пользователь ищет перевод или не знает, как сказать что-то по-немецки. "
            f"Дай перевод, краткое пояснение грамматики {expl_lang} и приведи 2–3 примера на немецком."
        )
    elif mode == "teacher":
        system = (
            "Ты учитель немецкого. Сначала ответь по-немецки (1–2 предложения), "
            f"затем отдельным блоком '{corrections_tag}' дай краткие исправления {expl_lang}. "
            f"Если ошибок нет — напиши '{no_errors}'."
        )
    elif mode == "mix":
        system = (
            "Ты собеседник на немецком. Отвечай коротко и естественно. "
            "Исправляй ошибки только если пользователь явно просит (например: 'исправь', 'korrigiere')."
        )
    elif mode == "auto":
        system = (
            "Ты собеседник на немецком. Отвечай естественно и коротко (1–2 предложения). "
            f"Если в сообщении ученика есть ошибки — добавь отдельный блок '{corrections_tag}' "
            f"с краткими пояснениями {expl_lang}. Если ошибок нет — просто ответь по-немецки."
        )
    else:
        system = "Ты собеседник на немецком. Отвечай естественно и коротко. Не исправляй и не объясняй."

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
    explain = ""

    if corrections_tag in full:
        parts = full.split(corrections_tag, 1)
        german_reply = parts[0].strip()
        tail = parts[1].strip()
        explain = f"{corrections_tag} {tail}" if tail else f"{corrections_tag} {no_errors}"

    return german_reply, explain

# === Language menu ===
def build_language_keyboard():
    kb = types.InlineKeyboardMarkup()
    row = []
    for code in LANGS:
        btn = types.InlineKeyboardButton(LANG_TITLES[code], callback_data=f"lang_{code}")
        row.append(btn)
        if len(row) == 3:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb

def send_language_menu(chat_id: int, lang: str):
    kb = build_language_keyboard()
    bot.send_message(chat_id, t(lang, "lang_choose"), reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("lang_"))
def cb_set_lang(call):
    code = call.data.split("_", 1)[1]
    set_lang(call.from_user.id, code)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, t(code, "lang_set").format(lang=LANG_TITLES[code]))
    bot.send_message(call.message.chat.id, t(code, "help"))

# === Команды утилиты/донат/язык/админ ===
@bot.message_handler(commands=['donate'])
def donate_cmd(message):
    send_donate_message(message.chat.id, get_lang(message.from_user.id), short=False)

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, format_admin_stats(7))
    else:
        bot.send_message(message.chat.id, t(get_lang(message.from_user.id), "admin_only"))

@bot.message_handler(commands=['language'])
def language_cmd(message):
    send_language_menu(message.chat.id, get_lang(message.from_user.id))

# === Команды режима/старт ===
@bot.message_handler(commands=['start', 'help'])
def start(message):
    # зарегистрируем визит
    if message.from_user.id not in user_stats:
        user_stats[message.from_user.id] = {"total": 0, "text": 0, "voice": 0, "first": utcnow(), "last": utcnow()}

    # если языка нет — показываем ОДНО сообщение на английском + клавиатуру
    if (message.text == "/start") and (message.from_user.id not in user_langs):
        kb = build_language_keyboard()
        bot.send_message(message.chat.id, t("en", "greet"), reply_markup=kb)
        return

    # иначе — обычная справка на выбранном языке
    lang = get_lang(message.from_user.id)
    bot.send_message(message.chat.id, t(lang, "help"))

@bot.message_handler(commands=['teacher_on'])
def teacher_on(message):
    set_mode(message.from_user.id, "teacher")
    bot.send_message(message.chat.id, t(get_lang(message.from_user.id), "mode_teacher_on"))

@bot.message_handler(commands=['teacher_off'])
def teacher_off(message):
    set_mode(message.from_user.id, "chat")
    bot.send_message(message.chat.id, t(get_lang(message.from_user.id), "mode_chat_on"))

@bot.message_handler(commands=['mix'])
def mix_mode(message):
    set_mode(message.from_user.id, "mix")
    bot.send_message(message.chat.id, t(get_lang(message.from_user.id), "mode_mix_on"))

@bot.message_handler(commands=['auto'])
def auto_mode(message):
    set_mode(message.from_user.id, "auto")
    bot.send_message(message.chat.id, t(get_lang(message.from_user.id), "mode_auto_on"))

@bot.message_handler(commands=['status'])
def status(message):
    lang = get_lang(message.from_user.id)
    labels = I18N[lang]["modes_labels"]
    mode = get_mode(message.from_user.id)
    bot.send_message(message.chat.id, t(lang, "status").format(mode=labels.get(mode, mode)))

# === Voice ===
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    lang = get_lang(message.from_user.id)
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

        de_answer, explain = generate_reply(user_text, mode, lang)

        bot.send_message(message.chat.id, de_answer)
        send_tts(message.chat.id, de_answer, base="voice_reply")

        if explain:
            bot.send_message(message.chat.id, f"✍️ {explain}")

        inc_and_maybe_remind(message.chat.id, message.from_user.id)

    except Exception:
        bot.send_message(message.chat.id, t(lang, "err_voice"))
        traceback.print_exc()

# === Text ===
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    lang = get_lang(message.from_user.id)
    try:
        bump_stats(message.from_user.id, "text")
        mode = get_mode(message.from_user.id)
        de_answer, explain = generate_reply(message.text, mode, lang)

        bot.send_message(message.chat.id, de_answer)
        send_tts(message.chat.id, de_answer, base="text_reply")

        if explain:
            bot.send_message(message.chat.id, f"✍️ {explain}")

        inc_and_maybe_remind(message.chat.id, message.from_user.id)

    except Exception:
        bot.send_message(message.chat.id, t(lang, "err_text"))
        traceback.print_exc()

print("🤖 Bot läuft...")
bot.polling(none_stop=True)
