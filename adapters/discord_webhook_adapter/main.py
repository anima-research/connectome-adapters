import asyncio
import logging
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from adapters.discord_webhook_adapter.adapter.adapter import Adapter
from core.rate_limiter.rate_limiter import RateLimiter
from core.socket_io.server import SocketIOServer
from core.utils.logger import setup_logging
from core.utils.config import Config

async def main():
    try:
        config = Config("adapters/discord_webhook_adapter/config/discord_webhook_config.yaml")
        RateLimiter.get_instance(config)
        setup_logging(config)

        logging.info("Starting Discord Webhook adapter")

        socketio_server = SocketIOServer(config)
        adapter = Adapter(config, socketio_server)
        socketio_server.set_adapter(adapter)

        from datetime import datetime

        await socketio_server.start()
        await adapter.start()
        while adapter.running:
            await asyncio.sleep(20)
    except (ValueError, FileNotFoundError) as e:
        print(f"Configuration error: {e}")
        print("Please ensure discord_webhook_config.yaml exists with required settings")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if adapter.running:
            await adapter.stop()
        await socketio_server.stop()

if __name__ == "__main__":
    asyncio.run(main())
