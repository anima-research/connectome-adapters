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

    def __init__(self, config: Config, content_required: bool = True):
        """Initialize with a Config instance

        Args:
            config: Config instance
            content_required: Whether to pass content to the event processor
        """
        self.config = config
        self.content_required = content_required
        self.rate_limiter = RateLimiter(config)
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.max_file_size = self.config.get_setting("attachments", "max_file_size_mb") * 1024 * 1024

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
                "size": attachment.size,
                "created_at": datetime.now(),
                "processable": False,
                "content": None
            }

            if attachment_metadata["size"] > self.max_file_size:
                logging.warning(f"Skipping download for {attachment.id} because it is too large")
            else:
                attachment_dir = os.path.join(
                    self.download_dir,
                    attachment_metadata["attachment_type"],
                    attachment_metadata["attachment_id"]
                )
                local_file_path = self._get_local_file_path(
                    attachment_dir,
                    attachment.filename,
                    attachment_metadata
                )

                if await self._download_file(attachment_dir, local_file_path, attachment):
                    attachment_metadata["processable"] = True
                    save_metadata_file(attachment_metadata, attachment_dir)

                    if self.content_required:
                        try:
                            with open(local_file_path, "rb") as f:
                                file_content = f.read()
                                attachment_metadata["content"] = base64.b64encode(file_content).decode("utf-8")
                        except Exception as e:
                            logging.error(f"Error reading file {local_file_path}: {e}")

            metadata.append(attachment_metadata)

        return metadata

    def _get_local_file_path(self,
                             attachment_dir: str,
                             attachment_name: str,
                             attachment: Dict[str, Any]) -> str:
        """Get the local file path for an attachment

        Args:
            attachment_dir: The directory of the attachment
            attachment_name: The filename of the attachment
            attachment: The attachment object

        Returns:
            The local file path for the attachment
        """
        file_name = attachment["attachment_id"]

        if "." in attachment_name:
            file_name += "." + attachment["file_extension"]

        return os.path.join(attachment_dir, file_name)

    async def _download_file(self,
                             attachment_dir: str,
                             local_file_path: str,
                             attachment: Dict[str, Any]) -> bool:
        """Download an attachment and save it to the local file system

        Args:
            attachment_dir: The directory of the attachment
            local_file_path: The local file path for the attachment
            attachment: The attachment object

        Returns:
            True if the attachment was downloaded, False otherwise
        """
        if not os.path.exists(local_file_path):
            try:
                create_attachment_dir(attachment_dir)
                await self.rate_limiter.limit_request("download")
                await attachment.save(local_file_path)
                logging.info(f"Downloaded {local_file_path}")
                return True
            except Exception as e:
                logging.error(f"Error downloading {attachment.id}: {e}")
                return False
        else:
            logging.info(f"Skipping download for {local_file_path} because it already exists")
            return True
