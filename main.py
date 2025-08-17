import os
import traceback
import requests
import telebot
from datetime import datetime
from openai import OpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in environment variables")

bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

def send_tts(chat_id: int, text: str, base: str = "reply"):
    """
    1) Пытаемся сделать OGG/Opus и отправить как voice (кружок).
    2) Если не вышло — делаем MP3 и отправляем как audio.
    """
    # ---- 1) OGG/Opus (voice) ----
    try:
        ogg_path = f"{base}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.ogg"
        with client.audio.speech.with_streaming_response.create(
            model="tts-1",          # стабильная TTS-модель
            voice="alloy",          # вариант: alloy, verse, coral, etc.
            input=text,
            response_format="opus"  # именно OGG/Opus для Telegram voice
        ) as resp:
            resp.stream_to_file(ogg_path)

        with open(ogg_path, "rb") as f:
            bot.send_voice(chat_id, f)
        return
    except Exception as e:
        print("OGG/Opus TTS failed, fallback to MP3:", e)
        traceback.print_exc()

    # ---- 2) MP3 (audio) ----
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

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 Hallo! Sprich mit mir auf Deutsch. Schick mir eine Sprachnachricht oder schreibe mir."
    )

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        file_info = bot.get_file(message.voice.file_id)
        file = requests.get(
            f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}',
            timeout=30
        )
        local_path = "voice.ogg"
        with open(local_path, "wb") as f:
            f.write(file.content)

        with open(local_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",  # можно заменить на whisper-1
                file=audio_file
            )

        user_text = getattr(transcript, "text", str(transcript))

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Du bist ein freundlicher Deutschlehrer. Antworte kurz und natürlich auf Deutsch und korrigiere Fehler mit einer kurzen Erklärung."},
                {"role": "user", "content": user_text},
            ],
        )
        answer = response.choices[0].message.content

        bot.send_message(message.chat.id, answer)           # текст
        send_tts(message.chat.id, answer, base="voice_reply")  # voice/audio

    except Exception as e:
        bot.send_message(message.chat.id, "Es gab einen Fehler bei der Verarbeitung der Sprachnachricht. Versuche es bitte noch einmal.")
        print("Voice handler error:", e)
        traceback.print_exc()

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Du bist ein freundlicher Deutschlehrer. Antworte kurz und natürlich auf Deutsch und korrigiere Fehler mit einer kurzen Erklärung."},
                {"role": "user", "content": message.text},
            ],
        )
        answer = response.choices[0].message.content

        bot.send_message(message.chat.id, answer)            # текст
        send_tts(message.chat.id, answer, base="text_reply") # voice/audio

    except Exception as e:
        bot.send_message(message.chat.id, "Entschuldige, da ist etwas schiefgelaufen. Bitte versuche es später erneut.")
        print("Text handler error:", e)
        traceback.print_exc()

print("🤖 Bot läuft...")
bot.polling(none_stop=True)
