import asyncio
import logging
import os
import shutil

from typing import Dict, Any
from datetime import datetime

from adapters.telegram_adapter.adapter.attachment_loaders.base_loader import BaseLoader
from core.utils.attachment_loading import (
    create_attachment_dir,
    delete_empty_directory,
    move_attachment,
    save_metadata_file
)
from core.utils.config import Config

class Uploader(BaseLoader):
    """Handles efficient file uploads to Telegram"""

    def __init__(self, config: Config, client):
        """Initialize with Config instance and Telethon client"""
        BaseLoader.__init__(self, config, client)

    async def upload_attachment(self,
                                conversation: Any,
                                attachment: Dict[str, Any]) -> Dict[str, Any]:
        """Upload a file to a Telegram chat

        Args:
            conversation: Telethon conversation object
            attachment: Attachment details (json)

        Returns:
            Dictionary with attachment metadata or {} if error
        """
        try:
            if not os.path.exists(attachment["file_path"]):
                logging.error(f"File not found: {attachment['file_path']}")
                return {}
            if attachment["size"] > self.max_file_size:
                logging.error(f"File exceeds Telegram's 2GB limit: {attachment['size']/1024/1024/1024:.2f} GB")
                return {}
            if not conversation:
                logging.error(f"Could not resolve conversation ID")
                return {}

            attachment_size = int(attachment["size"])
            upload_kwargs = {
                "file": attachment["file_path"],
                "force_document": attachment["attachment_type"] != "photo"
            }

            message = None
            if attachment_size > self.large_file_threshold:
                logging.info(f"Using chunked upload for large file: ({attachment_size/1024/1024:.2f} MB)")
                message = await self._upload_large_file(conversation, upload_kwargs)
            else:
                logging.info(f"Using standard upload for file: ({attachment_size/1024/1024:.2f} MB)")
                message = await self._upload_standard_file(conversation, upload_kwargs)
            metadata = await self._get_attachment_metadata(message)

            if metadata:
                attachment_dir = os.path.join(self.download_dir, metadata["attachment_type"], metadata["attachment_id"])
                create_attachment_dir(attachment_dir)
                save_metadata_file(metadata, attachment_dir)
                move_attachment(
                    attachment["file_path"],
                    os.path.join(attachment_dir, f"{metadata['attachment_id']}.{metadata['file_extension']}")
                )
                delete_empty_directory(attachment["file_path"])
                metadata["message"] = message

            return metadata
        except Exception as e:
            logging.error(f"Error uploading file: {str(e)}", exc_info=True)
            return {}

    async def _upload_standard_file(self, conversation: Any, upload_kwargs: Dict[str, Any]) -> Any:
        """Upload a file using standard method

        Args:
            conversation: Telethon conversation object
            upload_kwargs: Upload kwargs

        Returns:
            Telethon message object
        """
        try:
            start_time = datetime.now()
            result = await self.client.send_file(entity=conversation, **upload_kwargs)

            duration = (datetime.now() - start_time).total_seconds()
            file_size = os.path.getsize(upload_kwargs["file"])
            speed = file_size / duration / 1024 if duration > 0 else 0

            logging.info(f"Uploaded {file_size/1024:.2f} KB in {duration:.2f}s ({speed:.2f} KB/s)")
            return result
        except Exception as e:
            logging.error(f"Error in standard upload: {e}", exc_info=True)
            return None

    async def _upload_large_file(self, conversation: Any, upload_kwargs: Dict[str, Any]) -> Any:
        """Upload a large file with optimized settings and progress tracking

        Args:
            conversation: Telethon conversation object
            upload_kwargs: Upload kwargs

        Returns:
            Telethon message object
        """
        try:
            file_name = os.path.basename(upload_kwargs["file"])
            start_time = datetime.now()
            last_update_time = datetime.now()
            last_progress = 0

            async def progress(current, total):
                nonlocal last_update_time, last_progress
                now = datetime.now()
                if (now - last_update_time).total_seconds() >= 5:
                    percent = current * 100 / total if total else 0
                    logging.info(f"Uploading {file_name}: {current/1024/1024:.2f} MB of {total/1024/1024:.2f} MB "
                                 f"({percent:.1f}%)")
                    last_update_time = now
                    last_progress = current

            upload_kwargs["progress_callback"] = progress
            upload_kwargs["part_size_kb"] = 512  # Optimal chunk size
            upload_kwargs["use_cache"] = False  # Don't cache the file for large uploads

            result = await self.client.send_file(entity=conversation, **upload_kwargs)

            duration = (datetime.now() - start_time).total_seconds()
            logging.info(f"Large file upload complete: {os.path.getsize(upload_kwargs['file'])/1024/1024:.2f} MB "
                         f"in {duration:.2f}s")

            return result
        except Exception as e:
            logging.error(f"Error in large file upload: {e}", exc_info=True)
            return None
