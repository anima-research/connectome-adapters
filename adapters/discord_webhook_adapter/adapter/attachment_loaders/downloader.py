import aiohttp
import asyncio
import base64
import logging
import os
import re
import time

from datetime import datetime
from typing import Any, Dict, List

from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.attachment_loading import (
    create_attachment_dir,
    get_attachment_type_by_extension,
    save_metadata_file
)
from core.utils.config import Config

class Downloader():
    """Handles efficient file downloads from Discord"""

    def __init__(self, config: Config):
        """Initialize with a Config instance

        Args:
            config: Config instance
        """
        self.config = config
        self.rate_limiter = RateLimiter(config)
        self.download_dir = self.config.get_setting("attachments", "storage_dir")

    async def download_attachment(self, message: Any) -> List[Dict[str, Any]]:
        """Process attachments from a Discord message

        Args:
            message: Discord message object

        Returns:
            List of dictionaries with attachment metadata, empty list if no attachments
        """
        if not message or not hasattr(message, "attachments"):
            return []

        metadata = []

        for attachment in getattr(message, "attachments", []):
            file_extension = ""
            if "." in attachment.filename:
                file_extension = attachment.filename.split(".")[-1].lower()

            attachment_metadata = {
                "attachment_id": str(attachment.id),
                "attachment_type": get_attachment_type_by_extension(file_extension),
                "file_extension": file_extension,
                "created_at": datetime.now(),
                "size": attachment.size
            }
            attachment_dir = os.path.join(
                self.download_dir,
                attachment_metadata["attachment_type"],
                attachment_metadata["attachment_id"]
            )

            file_name = attachment_metadata["attachment_id"]
            if "." in attachment.filename:
                file_name += "." + attachment_metadata["file_extension"]

            local_file_path = os.path.join(attachment_dir, file_name)

            if not os.path.exists(local_file_path):
                try:
                    create_attachment_dir(attachment_dir)
                    await self.rate_limiter.limit_request("download")
                    await attachment.save(local_file_path)
                    logging.info(f"Downloaded {local_file_path}")
                except Exception as e:
                    logging.error(f"Error downloading {attachment_metadata['attachment_type']}: {e}")
                    continue
            else:
                logging.info(f"Skipping download for {local_file_path} because it already exists")

            save_metadata_file(attachment_metadata, attachment_dir)
            metadata.append(attachment_metadata)

        return metadata
