import asyncio
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

    def __init__(self, config: Config, client):
        """Initialize with Config instance and Telethon client"""
        BaseLoader.__init__(self, config, client)
        self.rate_limiter = RateLimiter.get_instance(self.config)

    async def download_attachment(self, message: Any, download_required: bool) -> Dict[str, Any]:
        """Process an attachment from a Telegram message

        Args:
            message: Telethon message object
            download_required: Whether to download the attachment

        Returns:
            Dictionary with attachment metadata or {} if no attachment
        """
        metadata = await self._get_attachment_metadata(message)

        if not metadata or not metadata["attachment_type"] or not metadata["attachment_id"]:
            return {}
        if not download_required:
            return metadata

        if metadata["file_extension"]:
            file_name = f"{metadata['attachment_id']}.{metadata['file_extension']}"
        else:
            file_name = f"{metadata['attachment_id']}"

        attachment_dir = os.path.join(self.download_dir, metadata["attachment_type"], metadata["attachment_id"])
        create_attachment_dir(attachment_dir)
        file_path = os.path.join(attachment_dir, file_name)

        if not os.path.exists(file_path):
            try:
                await self.rate_limiter.limit_request("download_attachment")
                if metadata["size"] and metadata["size"] > self.large_file_threshold:
                    logging.info(f"Using chunked download for large file ({metadata['size']/1024/1024:.2f} MB)")
                    await self._download_large_file(message, file_path)
                else:
                    logging.info(f"Using standard download for file")
                    await self._download_standard_file(message, file_path)
                save_metadata_file(metadata, attachment_dir)
                logging.info(f"Downloaded {metadata['attachment_type']} to {file_path}")
            except Exception as e:
                logging.error(f"Error downloading {metadata['attachment_type']}: {e}")
                return {}

        return metadata

    async def _download_standard_file(self, message: Any, file_path: str) -> None:
        """Download a file using standard download method

        Args:
            message: Telethon message object
            file_path: Path to save the file
        """
        try:
            start_time = datetime.now()
            downloaded_path = await self.client.download_media(message.media, file=file_path)
            duration = (datetime.now() - start_time).total_seconds()

            if os.path.exists(downloaded_path):
                logging.info(f"Downloaded {os.path.getsize(downloaded_path)/1024:.2f} KB in {duration:.2f}s")
        except Exception as e:
            logging.error(f"Error in standard download: {e}", exc_info=True)

    async def _download_large_file(self, message: Any, file_path: str) -> None:
        """Download a large file in chunks with resume capability

        Args:
            message: Telethon message object
            file_path: Path to save the file
        """
        try:
            temp_path = f"{file_path}.partial"
            offset = 0

            if os.path.exists(temp_path):
                offset = os.path.getsize(temp_path)
                logging.info(f"Resuming download from {offset/1024/1024:.2f} MB")

            with open(temp_path, "ab" if offset else "wb") as fd:
                start_time = datetime.now()
                chunk_size = 1024 * 1024  # 1 MB chunks
                last_update_time = datetime.now()
                last_offset = offset

                async def progress(current, total):
                    nonlocal last_update_time, last_offset
                    now = datetime.now()
                    if (now - last_update_time).total_seconds() >= 5:
                        percent = current * 100 / total if total else 0
                        logging.info(f"Downloaded {current/1024/1024:.2f} MB of {total/1024/1024:.2f} MB "
                                    f"({percent:.1f}%)")
                        last_update_time = now
                        last_offset = current

                await self.client.download_media(
                    message.media,
                    file=fd,
                    offset=offset,
                    progress_callback=progress,
                    part_size_kb=chunk_size // 1024  # Convert to KB
                )

            os.rename(temp_path, file_path)
            duration = (datetime.now() - start_time).total_seconds()
            logging.info(f"Large file download complete: {os.path.getsize(file_path)/1024/1024:.2f} MB "
                         f"in {duration:.2f}s")
        except Exception as e:
            logging.error(f"Error in large file download: {e}", exc_info=True)

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                logging.info(f"Partial download saved at {temp_path}")
