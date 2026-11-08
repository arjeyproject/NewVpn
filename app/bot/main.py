"""Telegram bot entrypoint — graceful when BOT_TOKEN is missing, resilient after restart."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.routers import admin, cloudflare, support, tutorials, user
from app.config import get_settings


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def run() -> None:
    setup_logging()
    s = get_settings()
    if not s.bot_token:
        log = logging.getLogger("newvpn.bot")
        log.warning("BOT_TOKEN is not configured — bot in standby. Set BOT_TOKEN in .env and restart.")
        while not get_settings().bot_token:
            await asyncio.sleep(60)
        s = get_settings()

    bot = Bot(token=s.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(user.router)
    dp.include_router(cloudflare.router)
    dp.include_router(tutorials.router)
    dp.include_router(support.router)
    dp.include_router(admin.router)

    logging.getLogger("newvpn.bot").info("NewVpn bot starting…")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
