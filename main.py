import telebot
import openai
import requests
import os
import traceback
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in environment variables")

bot = telebot.TeleBot(BOT_TOKEN)
openai.api_key = OPENAI_API_KEY

def tts_to_ogg(answer_text: str, base_filename: str = "reply") -> str:
    """
    Генерирует голос (OGG/Opus) через OpenAI TTS и возвращает путь к файлу.
    """
    # имя с таймстемпом, чтобы не затирать
    fname = f"{base_filename}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.ogg"

    # ⚠️ Новое API OpenAI: "audio.speech.create"
    audio = openai.audio.speech.create(
        model="gpt-4o-mini-tts",   # дешёвая и быстрая TTS-модель
        voice="alloy",             # голос (можно: alloy, verse, coral, etc.)
        input=answer_text,
        format="opus"              # просим Opus (Telegram voice понимает)
    )
    # audio содержимое — байты ogg/opus
    with open(fname, "wb") as f:
        f.write(audio)            # SDK отдаёт bytes-like

    return fname

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "👋 Hallo! Sprich mit mir auf Deutsch. Schick mir eine Sprachnachricht oder schreibe mir.")

# 🎤 обработка голосовых сообщений
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        file_info = bot.get_file(message.voice.file_id)
        file = requests.get(f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}', timeout=30)

        local_path = "voice.ogg"
        with open(local_path, "wb") as f:
            f.write(file.content)

        with open(local_path, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )

        user_text = transcript.text if hasattr(transcript, "text") else str(transcript)

        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Du bist ein freundlicher Deutschlehrer. Antworte kurz und natürlich auf Deutsch und korrigiere Fehler mit einer kurzen Erklärung."},
                {"role": "user", "content": user_text}
            ]
        )

        answer = response.choices[0].message.content

        # 1) Текстом
        bot.send_message(message.chat.id, answer)

        # 2) Голосом (OGG/Opus)
        try:
            ogg_path = tts_to_ogg(answer, base_filename="voice_reply")
            with open(ogg_path, "rb") as vf:
                bot.send_voice(message.chat.id, vf)
        except Exception as tts_err:
            # если TTS вдруг не сработал — просто молча пропускаем voice, в лог пишем
            print("TTS error:", tts_err)
            traceback.print_exc()

    except Exception as e:
        bot.send_message(message.chat.id, "Es gab einen Fehler bei der Verarbeitung der Sprachnachricht. Versuche es bitte noch einmal.")
        print("Voice handler error:", e)
        traceback.print_exc()

# ✍️ обработка текстовых сообщений
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Du bist ein freundlicher Deutschlehrer. Antworte kurz und natürlich auf Deutsch und korrigiere Fehler mit einer kurzen Erklärung."},
                {"role": "user", "content": message.text}
            ]
        )
        answer = response.choices[0].message.content

        # 1) Текстом
        bot.send_message(message.chat.id, answer)

        # 2) Голосом
        try:
            ogg_path = tts_to_ogg(answer, base_filename="text_reply")
            with open(ogg_path, "rb") as vf:
                bot.send_voice(message.chat.id, vf)
        except Exception as tts_err:
            print("TTS error:", tts_err)
            traceback.print_exc()

    except Exception as e:
        bot.send_message(message.chat.id, "Entschuldige, da ist etwas schiefgelaufen. Bitte versuche es später erneut.")
        print("Text handler error:", e)
        traceback.print_exc()

print("🤖 Bot läuft...")
bot.polling(none_stop=True)
