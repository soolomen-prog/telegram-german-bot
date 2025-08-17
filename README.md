# Telegram German Bot 🤖🇩🇪

Этот бот позволяет практиковать немецкий язык голосом.  
Он принимает voice-сообщения в Telegram, распознаёт их через OpenAI и отвечает на немецком.

## 🚀 Запуск

1. Создайте бота через @BotFather и получите `BOT_TOKEN`.
2. Получите API ключ OpenAI и сохраните его как `OPENAI_API_KEY`.
3. Запустите проект локально или на Render.

### Установка локально

```bash
git clone https://github.com/USERNAME/telegram-german-bot.git
cd telegram-german-bot
pip install -r requirements.txt
python main.py
```

### Деплой на Render

- Подключите репозиторий к Render
- Укажите переменные окружения:
  - `BOT_TOKEN`
  - `OPENAI_API_KEY`
- Запустите как Web Service (Background Worker)
