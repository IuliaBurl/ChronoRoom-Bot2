ChronoRoom — Lucky Dice Telegram Bot

A Telegram bot for discovering random people through short profile questionnaires and a "Lucky Dice" system.

📸 Demo

"ChronoRoom Bot Demo" (screenshots/demo.jpg)

✨ Features

- 🎲 Random profile discovery
- 📝 Profile creation with 5 randomly selected questions
- ❓ Question-based personal profiles
- 📸 Optional profile photo
- 🎯 Up to 3 profile discoveries per day
- 👤 Random selection of active profiles
- 💌 Anonymous messages through the bot
- ❤️ Contact requests and responses
- 🔄 Ability to create a new profile
- 💾 SQLite database
- 🔐 Telegram channel subscription check
- ⚡ Asynchronous architecture with Aiogram

🔄 How It Works

1. The user creates a profile by answering 5 randomly selected questions.
2. The user chooses a name and can optionally add a photo.
3. The user receives 3 "Lucky Dice" rolls per day.
4. Each roll selects a random active profile.
5. The user can send an anonymous message to the discovered person.
6. The recipient receives the sender's profile and can respond or reject the message.
7. Further interaction can lead to exchanging contact information.

🧩 Project Structure

ChronoRoom-Bot2/
├── README.md
├── screenshots/
│   └── demo.jpg
├── bot.py
├── config.py
├── database.py
├── handlers.py
├── questions.py
├── requirements.txt
└── utils.py

Files

- "bot.py" — bot entry point and polling
- "handlers.py" — Telegram handlers and interaction logic
- "database.py" — SQLite database and data operations
- "questions.py" — question pool used for profile creation
- "utils.py" — profile formatting and helper functions
- "config.py" — bot configuration
- "requirements.txt" — Python dependencies

🛠 Tech Stack

- Python 3
- Aiogram
- SQLite
- Telegram Bot API
- asyncio

💾 Data Storage

The bot uses SQLite to store user accounts, profiles, questionnaire answers, profile photos, daily roll information, and interactions between users.

🔒 Configuration

Private credentials such as the Telegram bot token should be provided through environment variables and must not be published to GitHub.

🚀 Running the Bot

Install dependencies:

pip install -r requirements.txt

Configure the required environment variables and run:

python bot.py

📌 About

ChronoRoom-Bot2 is one of several independent Telegram bots created for the ChronoRoom project.
