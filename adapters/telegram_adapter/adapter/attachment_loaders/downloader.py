import asyncio
import base64
import logging
import os

from typing import Any, Dict
from datetime import datetime

from adapters.telegram_adapter.adapter.attachment_loaders.base_loader import BaseLoader
from core.utils.attachment_loading import create_attachment_dir, save_metadata_file

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.config import Config

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
        attachment_metadata = await self._get_attachment_metadata(message)

        if not attachment_metadata or \
           not attachment_metadata["attachment_type"] or \
           not attachment_metadata["attachment_id"] or \
           not attachment_metadata["size"]:
            return {}

        if attachment_metadata["size"] > self.max_file_size:
            logging.warning(f"Skipping download for {attachment_metadata['attachment_id']} because it is too large")
            return attachment_metadata

        attachment_dir = os.path.join(
            self.download_dir,
            attachment_metadata["attachment_type"],
            attachment_metadata["attachment_id"]
        )
        local_file_path = self._get_local_file_path(attachment_dir, attachment_metadata)

        if await self._download_file(attachment_dir, local_file_path, message):
            attachment_metadata["processable"] = True
            save_metadata_file(attachment_metadata, attachment_dir)

            if self.content_required:
                try:
                    with open(local_file_path, "rb") as f:
                        file_content = f.read()
                        attachment_metadata["content"] = base64.b64encode(file_content).decode("utf-8")
                except Exception as e:
                    logging.error(f"Error reading file {local_file_path}: {e}")

        return attachment_metadata

    async def _download_file(self,
                             attachment_dir: str,
                             local_file_path: str,
                             message: Any) -> bool:
        """Download an attachment and save it to the local file system

        Args:
            attachment_dir: The directory of the attachment
            local_file_path: The local file path for the attachment
            message: The message object

        Returns:
            True if the attachment was downloaded, False otherwise
        """
        if not os.path.exists(local_file_path):
            try:
                create_attachment_dir(attachment_dir)
                await self.rate_limiter.limit_request("download")
                await self.client.download_media(message.media, file=local_file_path)
                logging.info(f"Downloaded {local_file_path}")
                return True
            except Exception as e:
                logging.error(f"Error downloading {local_file_path}: {e}")
                return False
        else:
            logging.info(f"Skipping download for {local_file_path} because it already exists")
            return True
