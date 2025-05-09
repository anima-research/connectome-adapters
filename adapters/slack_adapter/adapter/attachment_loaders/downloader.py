import aiohttp
import asyncio
import base64
import logging
import os

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
    """Handles efficient file downloads from Slack"""

    def __init__(self, config: Config, client: Any, content_required: bool = True):
        """Initialize with a Config instance

        Args:
            config: Config instance
            client: Slack web client instance
            content_required: Whether to pass content to the event processor
        """
        self.config = config
        self.client = client
        self.content_required = content_required
        self.rate_limiter = RateLimiter.get_instance(config)
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.max_file_size = self.config.get_setting("attachments", "max_file_size_mb") * 1024 * 1024

    async def download_attachments(self, message: Any) -> List[Dict[str, Any]]:
        """Process attachments from a Slack message

        Args:
            message: Slack message object

        Returns:
            List of dictionaries with attachment metadata, empty list if no attachments
        """
        if not message or "files" not in message or not message["files"]:
            return []

        metadata = []

        for file in message["files"]:
            file_extension = ""
            if "." in file.get("name", ""):
                file_extension = file["name"].split(".")[-1].lower()

            attachment_metadata = {
                "attachment_id": file["id"],
                "attachment_type": get_attachment_type_by_extension(file_extension),
                "file_extension": file_extension,
                "size": int(file["size"]),
                "created_at": datetime.now(),
                "processable": False,
                "content": None
            }

            if attachment_metadata["size"] > self.max_file_size:
                logging.warning(f"Skipping download for {file['id']} because it is too large")
            else:
                attachment_dir = os.path.join(
                    self.download_dir,
                    attachment_metadata["attachment_type"],
                    attachment_metadata["attachment_id"]
                )
                local_file_path = self._get_local_file_path(attachment_dir, attachment_metadata)

                if await self._download_file(attachment_dir, local_file_path, attachment_metadata):
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
                             attachment: Dict[str, Any]) -> str:
        """Get the local file path for an attachment

        Args:
            attachment_dir: The directory of the attachment
            attachment: The attachment object

        Returns:
            The local file path for the attachment
        """
        file_name = attachment["attachment_id"]

        if attachment["file_extension"]:
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

                response = await self.client.files_info(file=attachment["attachment_id"])
                download_url = response["file"]["url_private"]
                headers = {"Authorization": f"Bearer {self.client.token}"}

                async with aiohttp.ClientSession() as session:
                    async with session.get(download_url, headers=headers) as response:
                        response.raise_for_status()
                        with open(local_file_path, "wb") as f:
                            f.write(await response.read())

                logging.info(f"Downloaded {local_file_path}")
                return True
            except Exception as e:
                logging.error(f"Error downloading {attachment['attachment_type']}: {e}")
                return False
        else:
            logging.info(f"Skipping download for {local_file_path} because it already exists")
            return True
