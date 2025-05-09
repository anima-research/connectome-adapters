import asyncio
import logging
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from adapters.slack_adapter.adapter.adapter import Adapter
from core.rate_limiter.rate_limiter import RateLimiter
from core.socket_io.server import SocketIOServer
from core.utils.logger import setup_logging
from core.utils.config import Config
from core.utils.emoji_converter import EmojiConverter

async def main():
    try:
        config = Config("adapters/slack_adapter/config/slack_config.yaml")
        EmojiConverter.get_instance(config)
        RateLimiter.get_instance(config)
        setup_logging(config)

        logging.info("Starting Slack adapter")

        socketio_server = SocketIOServer(config)
        adapter = Adapter(config, socketio_server, start_maintenance=True)
        socketio_server.set_adapter(adapter)

        await socketio_server.start()
        await adapter.start()
        while adapter.running:
            await asyncio.sleep(20)
    except (ValueError, FileNotFoundError) as e:
        print(f"Configuration error: {e}")
        print("Please ensure slack_config.yaml exists with required settings")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if adapter.running:
            await adapter.stop()
        await socketio_server.stop()

if __name__ == "__main__":
    asyncio.run(main())
