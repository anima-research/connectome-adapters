import aiohttp
import asyncio
import base64
import logging
import magic
import os
import re
import time

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.adapters.zulip_adapter.event_processing.attachment_loaders.base_loader import BaseLoader
from src.core.utils.attachment_loading import (
    create_attachment_dir,
    get_attachment_type_by_extension,
    save_metadata_file
)
from src.core.utils.config import Config

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
        attachments_metadata = []

        for filename, file_path in self._get_attachments_list(message):
            metadata = self._get_initial_metadata(filename, file_path)

            attachment_dir = os.path.join(
                self.download_dir,
                metadata["attachment_type"],
                metadata["attachment_id"]
            )
            local_file_path = os.path.join(attachment_dir, metadata["filename"])

            if not os.path.exists(local_file_path):
                create_attachment_dir(attachment_dir)
                await self._download_file(metadata["url"], local_file_path)
            else:
                logging.info(f"Skipping download for {local_file_path} because it already exists")

            metadata["size"] = os.path.getsize(local_file_path)
            mime = magic.Magic(mime=True)
            metadata["content_type"] = mime.from_file(local_file_path)

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

            attachments_metadata.append(metadata)

        return attachments_metadata

    def _get_attachments_list(self, message: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Extract attachment information from a Zulip message

        Args:
            message: Zulip message object

        Returns:
            List of attachment filenames and file_paths, empty list if no attachments
        """
        if not message or "content" not in message:
            return []

        content = message.get("content", "")
        attachments = []

        for match in re.finditer(self.ATTACHMENT_PATTERN, content):
            filename = match.group(1)
            file_path = match.group(2)

            if filename and file_path:
                attachments.append((filename, file_path))

        return attachments

    def _get_local_filename(self,
                            attachment_id: str,
                            file_extension: Optional[str] = None) -> str:
        """Get the local file name for an attachment

        Args:
            attachment_id: The ID of the attachment
            file_extension: The file extension of the attachment

        Returns:
            The local file name for the attachment
        """
        file_name = attachment_id

        if file_extension:
            file_name += "." + file_extension

        return file_name

    def _get_download_url(self, file_path: str) -> str:
        """Get the download URL for an attachment

        Args:
            file_path: The file path of the attachment

        Returns:
            Download URL
        """
        api_key = self._get_api_key()
        url = f"{self.zulip_site}{file_path}"
        return url + ("?" if "?" not in url else "&") + f"api_key={api_key}"

    def _get_initial_metadata(self, filename: str, file_path: str) -> Dict[str, Any]:
        """Get the initial metadata for an attachment

        Args:
            filename: The filename of the attachment
            file_path: The file path of the attachment

        Returns:
            Initial metadata for the attachment (size, content type)
        """
        attachment_id = self._generate_attachment_id(file_path)

        file_extension = os.path.splitext(filename)[1].lower().lstrip(".")
        if not file_extension:
            file_extension = None

        return {
            "attachment_id": attachment_id,
            "attachment_type": get_attachment_type_by_extension(file_extension),
            "filename": self._get_local_filename(attachment_id, file_extension),
            "file_path": file_path,
            "size": None,  # Size isn't available until after download,
            "content_type": None, # Content type isn't available until after download
            "content": None,
            "url": self._get_download_url(file_path),
            "created_at": datetime.now(),
            "processable": False
        }

    async def _download_file(self, download_url: str, file_path: str) -> None:
        """Download a file using standard download method

        Args:
            download_url: The URL to download the file from
            file_path: Path to save the file
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(download_url, timeout=30) as response:
                    if response.status != 200:
                        content = await response.text()
                        logging.error(f"Download failed: HTTP {response.status}, Response: {content[:200]}")
                        return

                    with open(file_path, "wb") as f:
                        while True:
                            chunk = await response.content.read(self.chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)

            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                logging.info(f"Downloaded file successfully: {os.path.getsize(file_path)/1024:.2f} KB")
                return

            logging.error("Download appeared to succeed but file is empty or missing")
            return
        except Exception as e:
            logging.error(f"Error downloading file: {e}", exc_info=True)
            return
