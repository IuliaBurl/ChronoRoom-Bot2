import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = ""

CHANNEL_USERNAME = ""
MAX_ANSWER_LENGTH = 200
MAX_DAILY_ROLLS = 3
MAX_NAME_LENGTH = 50
QUESTIONS_COUNT = 5
