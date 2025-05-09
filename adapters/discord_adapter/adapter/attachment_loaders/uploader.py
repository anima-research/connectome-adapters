import base64
import discord
import logging
import os
import shutil
import uuid

from typing import Any, List, Tuple
from core.utils.config import Config

class Uploader():
    """Prepares files for upload to Discord"""

    def __init__(self, config: Config):
        """Initialize with a Discord client

        Args:
            config: Config instance
        """
        self.config = config
        self.max_file_size = self.config.get_setting(
            "attachments", "max_file_size_mb"
        ) * 1024 * 1024  # Convert to bytes
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

    def upload_attachment(self, attachments: List[Any]) -> Tuple[List[str], List[str]]:
        """Upload a file to Discord

        Args:
            attachments: List of attachment details (json)

        Returns:
            List of discord.File objects or [] if error
        """
        files = []
        paths = []

        try:
            for attachment in attachments:
                try:
                    file_content = base64.b64decode(attachment.content)
                except Exception as e:
                    logging.error(f"Failed to decode base64 content: {e}")
                    continue

                if len(file_content) > self.max_file_size:
                    logging.error(f"Decoded content exceeds size limit: {len(file_content)/1024/1024:.2f} MB")
                    continue

                temp_path = os.path.join(self.temp_dir, attachment.file_name)
                with open(temp_path, "wb") as f:
                    f.write(file_content)

                files.append(discord.File(temp_path))
                paths.append(temp_path)

            return files, paths
        except Exception as e:
            logging.error(f"Error uploading file: {str(e)}", exc_info=True)
            return [], []

    def clean_up_uploaded_files(self, attachments: List[str]) -> None:
        """Clean up files after they have been uploaded to Discord

        Args:
            attachments: List of attachment details (json)
        """
        for attachment in attachments:
            os.remove(attachment)
