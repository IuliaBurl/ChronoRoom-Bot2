import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").lstrip("@")

MAX_ANSWER_LENGTH = 200
MAX_DAILY_ROLLS = 3
MAX_NAME_LENGTH = 50
MAX_MESSAGE_LENGTH = 1000
