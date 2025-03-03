import asyncio
import logging
import sys

from telegram.error import TimedOut, NetworkError

from logger import setup_logging
from config import Config
from telegram_bot import TelegramBot
from socket_io_server import SocketIOServer

async def main():
    setup_logging()
    logging.info("Starting Telegram adapter")

    socketio_server = SocketIOServer()
    bot = TelegramBot(socketio_server)

    socketio_server.set_telegram_bot(bot)

    try:
        await socketio_server.start()
        await bot.start()
        while bot.running:
            await asyncio.sleep(1)
    except (TimedOut, NetworkError) as e:
        logging.error(f"Network error: {e}")
        logging.error("Could not connect to Telegram. Please check your internet connection.")
    except (ValueError, FileNotFoundError) as e:
        logging.error(f"Configuration error: {e}")
        logging.error("Please ensure telegram_config.yaml exists with required settings")
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        if bot.running:
            await bot.stop()
        await socketio_server.stop()

if __name__ == "__main__":
    asyncio.run(main())
