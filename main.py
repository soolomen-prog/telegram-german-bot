import telebot
import openai
import requests
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
openai.api_key = OPENAI_API_KEY

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "👋 Hallo! Sprich mit mir auf Deutsch.")

# 🎤 обработка голосовых сообщений
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    file_info = bot.get_file(message.voice.file_id)
    file = requests.get(f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}')

    with open("voice.ogg", "wb") as f:
        f.write(file.content)

    audio_file = open("voice.ogg", "rb")
    transcript = openai.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=audio_file
    )

    # создаём ответ
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Du bist ein freundlicher Deutschlehrer. Antworte auf Deutsch und korrigiere Fehler."},
            {"role": "user", "content": transcript.text}
        ]
    )

    answer = response.choices[0].message.content
    bot.send_message(message.chat.id, answer)

print("🤖 Bot läuft...")
bot.polling()
