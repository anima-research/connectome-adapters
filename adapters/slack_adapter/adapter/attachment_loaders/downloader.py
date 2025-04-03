import aiohttp
import asyncio
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

    def __init__(self, config: Config, client: Any):
        """Initialize with a Config instance

        Args:
            config: Config instance
            client: Slack web client instance
        """
        self.config = config
        self.client = client
        self.rate_limiter = RateLimiter.get_instance(config)
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.chunk_size = 8 * 1024 * 1024  # 8MB chunks for large files

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
                "created_at": datetime.now(),
                "size": file.get("size", 0)
            }
            attachment_dir = os.path.join(
                self.download_dir,
                attachment_metadata["attachment_type"],
                attachment_metadata["attachment_id"]
            )

            file_name = attachment_metadata["attachment_id"]
            if file_extension:
                file_name += "." + file_extension

            local_file_path = os.path.join(attachment_dir, file_name)

            if not os.path.exists(local_file_path):
                try:
                    create_attachment_dir(attachment_dir)
                    await self.rate_limiter.limit_request("download")

                    if attachment_metadata["size"] < 10 * 1024 * 1024:  # < 10MB
                        await self._download_standard_file(file["id"], local_file_path)
                    else:
                        await self._download_large_file(file, local_file_path)

                    logging.info(f"Downloaded {local_file_path}")
                except Exception as e:
                    logging.error(f"Error downloading {attachment_metadata['attachment_type']}: {e}")
                    continue
            else:
                logging.info(f"Skipping download for {local_file_path} because it already exists")

            save_metadata_file(attachment_metadata, attachment_dir)
            metadata.append(attachment_metadata)

        return metadata

    async def _download_standard_file(self, file_id: str, file_path: str) -> None:
        """Download small files directly using the Slack SDK

        Args:
            file_id: Slack file ID
            file_path: Path to save the file
        """
        response = await self.client.files_info(file=file_id)
        download_url = response["file"]["url_private"]
        headers = {"Authorization": f"Bearer {self.client.token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(download_url, headers=headers) as response:
                response.raise_for_status()
                with open(file_path, "wb") as f:
                    f.write(await response.read())

    async def _download_large_file(self, file_info: Dict[str, Any], file_path: str) -> None:
        """Download large files in chunks with resumption support

        Args:
            file_info: File info dictionary from Slack API
            file_path: Path to save the file
        """
        download_url = file_info["url_private"]
        total_size = file_info["size"]
        headers = {"Authorization": f"Bearer {self.client.token}"}
        start_byte = 0

        if os.path.exists(file_path):
            start_byte = os.path.getsize(file_path)
            if start_byte >= total_size:
                return  # Already downloaded
            headers["Range"] = f"bytes={start_byte}-"

        timeout = aiohttp.ClientTimeout(total=1800) # 30 minutes

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(download_url, headers=headers) as response:
                response.raise_for_status()

                mode = "ab" if start_byte > 0 else "wb"
                with open(file_path, mode) as f:
                    bytes_downloaded = start_byte
                    async for chunk in response.content.iter_chunked(self.chunk_size):
                        f.write(chunk)
                        bytes_downloaded += len(chunk)

                        if total_size > 100 * 1024 * 1024:  # > 100MB
                            progress = min(100, int(bytes_downloaded * 100 / total_size))
                            if progress % 20 == 0:  # Log every 20%
                                logging.info(f"Downloading {file_info['id']}: {progress}% complete")
