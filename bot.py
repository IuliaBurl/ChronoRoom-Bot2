import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
import handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    # HTML is the default parse mode for every message the bot sends.
    # User-supplied text is escaped with utils.escape_html().
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(handlers.router)

    logger.info("The bot has been launched!")
    try:
        await dp.start_polling(bot)
    finally:
        await storage.close()
        await bot.session.close()
        handlers.db.close()


if __name__ == "__main__":
    asyncio.run(main())
