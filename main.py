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

def send_tts(chat_id: int, text: str, base: str = "reply"):
    """
    Пытаемся отправить голос:
    1) OGG/Opus -> send_voice (кружок)
    2) Если не получилось -> MP3 -> send_audio (карточка)
    """
    # 1) OGG/Opus (Telegram voice)
    try:
        ogg_path = f"{base}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.ogg"
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
            format="opus"
        ) as resp:
            resp.stream_to_file(ogg_path)
        with open(ogg_path, "rb") as f:
            bot.send_voice(chat_id, f)
        return
    except Exception as e:
        print("OGG/Opus TTS failed, fallback to MP3:", e)
        traceback.print_exc()

    # 2) Fallback MP3 (обычное аудио)
    try:
        mp3_path = f"{base}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.mp3"
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
            format="mp3"
        ) as resp:
            resp.stream_to_file(mp3_path)
        with open(mp3_path, "rb") as f:
            bot.send_audio(chat_id, f, title="Antwort (TTS)")
    except Exception as e2:
        print("MP3 TTS also failed:", e2)
        traceback.print_exc()

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

        # 2) Голосом
        send_tts(message.chat.id, answer, base="voice_reply")

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
        send_tts(message.chat.id, answer, base="text_reply")

    except Exception as e:
        bot.send_message(message.chat.id, "Entschuldige, da ist etwas schiefgelaufen. Bitte versuche es später erneut.")
        print("Text handler error:", e)
        traceback.print_exc()

print("🤖 Bot läuft...")
bot.polling(none_stop=True)
