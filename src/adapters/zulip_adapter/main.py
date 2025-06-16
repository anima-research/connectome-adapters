import asyncio
import logging
import signal
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.adapters.zulip_adapter.adapter import Adapter
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.socket_io.server import SocketIOServer
from src.core.utils.config import Config
from src.core.utils.logger import setup_logging
from src.core.utils.emoji_converter import EmojiConverter

should_shutdown = False

def shutdown():
    """Perform graceful shutdown when signal is received"""
    global should_shutdown
    logging.warning("Shutdown signal received, initiating shutdown...")
    should_shutdown = True

async def main():
    try:
        config = Config("config/zulip_config.yaml")
        RateLimiter.get_instance(config)
        EmojiConverter.get_instance(config)
        setup_logging(config)

        logging.info("Starting Zulip adapter")

        socketio_server = SocketIOServer(config)
        adapter = Adapter(config, socketio_server, start_maintenance=True)
        socketio_server.set_adapter(adapter)

        if sys.platform != "win32":
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, shutdown)
        else:
            # On Windows, use signal.signal instead
            signal.signal(signal.SIGINT, lambda s, f: shutdown())
            signal.signal(signal.SIGTERM, lambda s, f: shutdown())

        await socketio_server.start()
        await adapter.start()
        while adapter.running and not should_shutdown:
            await asyncio.sleep(1)
    except (ValueError, FileNotFoundError) as e:
        logging.error(f"Configuration error: {e}")
        logging.error("Please ensure zulip_config.yaml exists with required settings")
    except Exception as e:
        import traceback
        print(f"Unexpected error: {e}")
        print("Full traceback:")
        traceback.print_exc()
    finally:
        if adapter.running:
            await adapter.stop()
        await socketio_server.stop()

if __name__ == "__main__":
    asyncio.run(main())
