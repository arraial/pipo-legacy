#!usr/bin/env python3
import asyncio
import logging
import os
import sys
import signal

from pipo.signal_manager import SignalManager
from pipo.bot import PipoBot
from pipo.cogs.music_bot import MusicBot
from pipo.config import settings
from pipo.player.music_queue._remote_music_queue import broker, declare_dlx


async def run_bot():
    channel = settings.channel
    voice_channel = settings.voice_channel
    token = settings.token

    asyncio.current_task().set_name(settings.main_task_name)
    SignalManager.add_handlers(
        asyncio.get_event_loop(),
        settings.main_task_name,
        (signal.SIGUSR1, signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT),
    )

    bot = PipoBot(
        command_prefix=settings.commands.prefix, description=settings.bot_description
    )
    await broker.connect()
    await declare_dlx(broker)
    await broker.start()

    async with bot:
        await bot.add_cog(MusicBot(bot, channel, voice_channel))
        await bot.start(token)


def main():
    logging.basicConfig(
        level=settings.log.level,
        format=settings.log.format,
        encoding=settings.log.encoding,
    )

    logger = logging.getLogger(__name__)

    try:
        asyncio.run(run_bot())
    except Exception:
        logger.exception("Unexpected exception raised")
    finally:
        logger.info("Exiting program")
        sys.stderr.flush()
        os._exit(1)


if __name__ == "__main__":
    main()
