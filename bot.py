import asyncio

import logging

from aiogram import Bot, Dispatcher

from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN

import handlers


logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(name)


async def main():

bot = Bot(token=BOT_TOKEN)

storage = MemoryStorage()

dp = Dispatcher(storage=storage)


dp.include_router(handlers.router)  

logger.info("The bot has been launched!")  
try:  
    await dp.start_polling(bot)  
finally:  
    await storage.close()  
    await bot.session.close()  



if name == "main":

asyncio.run(main())
