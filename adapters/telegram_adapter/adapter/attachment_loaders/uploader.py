import asyncio
import base64
import logging
import os
import shutil

from typing import Dict, Any
from datetime import datetime

from adapters.telegram_adapter.adapter.attachment_loaders.base_loader import BaseLoader
from core.utils.attachment_loading import (
    create_attachment_dir,
    move_attachment,
    save_metadata_file
)
from core.utils.config import Config

class Uploader(BaseLoader):
    """Handles efficient file uploads to Telegram"""

    def __init__(self, config: Config, client):
        """Initialize with Config instance and Telethon client"""
        BaseLoader.__init__(self, config, client)
        self.temp_dir = os.path.join(
            self.config.get_setting("attachments", "storage_dir"),
            "tmp_uploads"
        )
        os.makedirs(self.temp_dir, exist_ok=True)

    def __del__(self):
        """Cleanup the temporary directory when object is garbage collected"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logging.info(f"Removed temporary upload directory: {self.temp_dir}")
        except Exception as e:
            logging.error(f"Error removing temporary directory: {e}")

    async def upload_attachment(self, conversation: Any, attachment: Any) -> Dict[str, Any]:
        """Upload a file to a Telegram chat

        Args:
            conversation: Telethon conversation object
            attachment: Attachment details

        Returns:
            Dictionary with attachment metadata or {} if error
        """
        try:
            if not conversation:
                logging.error(f"Could not resolve conversation ID")
                return {}

            try:
                file_content = base64.b64decode(attachment.content)
            except Exception as e:
                logging.error(f"Failed to decode base64 content: {e}")
                return {}

            if len(file_content) > self.max_file_size:
                logging.error(f"Decoded content exceeds size limit: {len(file_content)/1024/1024:.2f} MB")
                return {}

            temp_path = os.path.join(self.temp_dir, attachment.file_name)
            with open(temp_path, "wb") as f:
                f.write(file_content)

            message = await self.client.send_file(entity=conversation, file=temp_path)
            attachment_metadata = await self._get_attachment_metadata(message)

            if attachment_metadata:
                attachment_metadata["processable"] = True
                attachment_metadata["message"] = message
                attachment_dir = os.path.join(
                    self.download_dir,
                    attachment_metadata["attachment_type"],
                    attachment_metadata["attachment_id"]
                )
                local_file_path = self._get_local_file_path(attachment_dir, attachment_metadata)

                create_attachment_dir(attachment_dir)
                save_metadata_file(attachment_metadata, attachment_dir)
                move_attachment(temp_path, local_file_path)

            return attachment_metadata
        except Exception as e:
            logging.error(f"Error uploading file: {str(e)}", exc_info=True)
            return {}
