import asyncio
import base64
import logging
import magic
import os

from typing import Any, Dict
from datetime import datetime

from src.adapters.telegram_adapter.attachment_loaders.base_loader import BaseLoader
from src.core.utils.attachment_loading import create_attachment_dir, save_metadata_file

from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

class Downloader(BaseLoader):
    """Handles efficient file downloads from Telegram"""

    def __init__(self, config: Config, client: Any, content_required: bool = True):
        """Initialize with Config instance and Telethon client

        Args:
            config: Config instance
            client: Telethon client instance
            content_required: Whether to pass content to the event processor
        """
        BaseLoader.__init__(self, config, client)
        self.content_required = content_required
        self.rate_limiter = RateLimiter.get_instance(self.config)

    async def download_attachment(self, message: Any) -> Dict[str, Any]:
        """Process an attachment from a Telegram message

        Args:
            message: Telethon message object

        Returns:
            Dictionary with attachment metadata or {} if no attachment
        """
        metadata = await self._get_attachment_metadata(message)

        if not metadata or not metadata["attachment_id"]:
            return {}
        if metadata["size"] > self.max_file_size:
            logging.warning(f"Skipping download for {metadata['attachment_id']} because it is too large")
            return metadata

        attachment_dir = os.path.join(self.download_dir, metadata["attachment_type"], metadata["attachment_id"])
        local_file_path = os.path.join(attachment_dir, metadata["filename"])

        if not os.path.exists(local_file_path):
            create_attachment_dir(attachment_dir)
            await self.rate_limiter.limit_request("download")
            await self.client.download_media(message.media, file=local_file_path)
        else:
            logging.info(f"Skipping download for {local_file_path} because it already exists")

        mime = magic.Magic(mime=True)
        metadata["content_type"] = mime.from_file(local_file_path)
        metadata["processable"] = True

        save_metadata_file(metadata, attachment_dir)

        if self.content_required:
            try:
                with open(local_file_path, "rb") as f:
                    file_content = f.read()
                    metadata["content"] = base64.b64encode(file_content).decode("utf-8")
            except Exception as e:
                logging.error(f"Error reading file {local_file_path}: {e}")

        return metadata
