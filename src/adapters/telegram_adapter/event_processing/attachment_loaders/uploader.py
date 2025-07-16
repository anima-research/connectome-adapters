import asyncio
import base64
import logging
import magic
import os
import shutil

from typing import Any, Dict, Optional
from src.adapters.telegram_adapter.event_processing.attachment_loaders.base_loader import BaseLoader
from src.core.utils.attachment_loading import (
    create_attachment_dir,
    move_attachment,
    save_metadata_file
)
from src.core.utils.config import Config

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

    async def upload_attachment(self,
                                conversation: Any,
                                attachment: Any,
                                reply_to: Optional[int] = None) -> Dict[str, Any]:
        """Upload a file to a Telegram chat

        Args:
            conversation: Telethon conversation object
            attachment: Attachment details
            reply_to: Message ID to reply to

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

            message = await self.client.send_file(entity=conversation, file=temp_path, reply_to=reply_to)
            metadata = await self._get_attachment_metadata(message)

            if metadata:
                metadata["processable"] = True
                metadata["message"] = message

                attachment_dir = os.path.join(
                    self.download_dir,
                    metadata["attachment_type"],
                    metadata["attachment_id"]
                )
                local_file_path = os.path.join(attachment_dir, metadata["filename"])
                create_attachment_dir(attachment_dir)
                move_attachment(temp_path, local_file_path)

                mime = magic.Magic(mime=True)
                metadata["content_type"] = mime.from_file(local_file_path)
                save_metadata_file(metadata, attachment_dir)

            return metadata
        except Exception as e:
            logging.error(f"Error uploading file: {str(e)}", exc_info=True)
            return {}
