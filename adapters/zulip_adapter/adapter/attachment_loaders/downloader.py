import aiohttp
import asyncio
import base64
import logging
import os
import re
import time

from datetime import datetime
from typing import Any, Dict, List

from adapters.zulip_adapter.adapter.attachment_loaders.base_loader import BaseLoader
from core.utils.attachment_loading import (
    create_attachment_dir,
    get_attachment_type_by_extension,
    save_metadata_file
)
from core.utils.config import Config

class Downloader(BaseLoader):
    """Handles efficient file downloads from Zulip"""

    # Regex pattern to match [filename](/user_uploads/path/to/file)
    ATTACHMENT_PATTERN = r'\[([^\]]+)\]\((/user_uploads/[^)]+)\)'

    def __init__(self, config: Config, client: Any, content_required: bool = True):
        """Initialize with Config instance

        Args:
            config: Config instance
            client: Zulip client instance
            content_required: Whether to download the content of the attachment
        """
        super().__init__(config, client)
        self.chunk_size = self.config.get_setting("adapter", "chunk_size")
        self.content_required = content_required

    async def download_attachment(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process attachments from a Zulip message

        Args:
            message: Zulip message object

        Returns:
            List of dictionaries with attachment metadata, empty list if no attachments
        """
        attachments_metadata = await self._get_attachment_metadata(message)
        result_metadata = []

        if not attachments_metadata:
            return []

        for metadata in attachments_metadata:
            attachment_dir = os.path.join(self.download_dir, metadata["attachment_type"], metadata["attachment_id"])
            local_file_path = self._get_local_file_path(attachment_dir, metadata)

            if not os.path.exists(local_file_path):
                create_attachment_dir(attachment_dir)
                await self._download_file(metadata, local_file_path)
            else:
                logging.info(f"Skipping download for {local_file_path} because it already exists")

            metadata["size"] = os.path.getsize(local_file_path)

            if metadata["size"] <= self.max_file_size:
                metadata["processable"] = True
                save_metadata_file(metadata, attachment_dir)

                if self.content_required:
                    try:
                        with open(local_file_path, "rb") as f:
                            file_content = f.read()
                            metadata["content"] = base64.b64encode(file_content).decode("utf-8")
                    except Exception as e:
                        logging.error(f"Error reading file {local_file_path}: {e}")

            result_metadata.append(metadata)

        return result_metadata

    async def _get_attachment_metadata(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract attachment information from a Zulip message

        Args:
            message: Zulip message object

        Returns:
            List of attachment metadata dictionaries, empty list if no attachments
        """
        if not message or "content" not in message:
            return []

        content = message.get("content", "")
        attachments = []

        for match in re.finditer(self.ATTACHMENT_PATTERN, content):
            filename = match.group(1)
            file_path = match.group(2)

            if not file_path or not filename:
                continue

            file_extension = os.path.splitext(filename)[1].lower().lstrip(".")
            if not file_extension:
                file_extension = None

            attachment_id = self._generate_attachment_id(file_path)
            metadata = {
                "attachment_type": get_attachment_type_by_extension(file_extension),
                "attachment_id": attachment_id,
                "file_name": filename,
                "file_extension": file_extension,
                "file_path": file_path,
                "created_at": datetime.now(),
                "size": None,  # Size isn't available until after download,
                "processable": False,
                "content": None
            }

            attachments.append(metadata)

        return attachments

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

    async def _download_file(self, metadata: Dict[str, Any], file_path: str) -> bool:
        """Download a file using standard download method

        Args:
            metadata: Attachment metadata
            file_path: Path to save the file

        Returns:
            True if download was successful, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._get_download_url(metadata), timeout=30) as response:
                    if response.status != 200:
                        content = await response.text()
                        logging.error(f"Download failed: HTTP {response.status}, Response: {content[:200]}")
                        return False

                    with open(file_path, "wb") as f:
                        while True:
                            chunk = await response.content.read(self.chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)

            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                logging.info(f"Downloaded file successfully: {os.path.getsize(file_path)/1024:.2f} KB")
                return True

            logging.error("Download appeared to succeed but file is empty or missing")
            return False
        except Exception as e:
            logging.error(f"Error downloading file: {e}", exc_info=True)
            return False

    def _get_download_url(self, metadata: Dict[str, Any]) -> str:
        """Get the download URL for an attachment

        Args:
            metadata: Attachment metadata

        Returns:
            Download URL
        """
        api_key = self._get_api_key()
        url = f"{self.zulip_site}{metadata['file_path']}"
        return url + ("?" if "?" not in url else "&") + f"api_key={api_key}"
