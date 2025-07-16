import aiohttp
import asyncio
import base64
import logging
import magic
import os
import shutil

from typing import Dict, Any, Optional
from src.adapters.zulip_adapter.event_processing.attachment_loaders.base_loader import BaseLoader
from src.core.utils.attachment_loading import (
    create_attachment_dir,
    get_attachment_type_by_extension,
    move_attachment
)
from src.core.utils.config import Config

class Uploader(BaseLoader):
    """Handles efficient file uploads to Zulip"""

    def __init__(self, config: Config, client: Any):
        """Initialize with Config instance and Zulip client

        Args:
            config: Config instance
            client: Zulip client
        """
        super().__init__(config, client)
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

    async def upload_attachment(self, attachment: Any) -> Optional[str]:
        """Upload a file to Zulip

        Args:
            attachment: Attachment details

        Returns:
            Dictionary with attachment metadata or {} if error
        """
        try:
            try:
                file_content = base64.b64decode(attachment.content)
            except Exception as e:
                logging.error(f"Failed to decode base64 content: {e}")
                return None

            if len(file_content) > self.max_file_size:
                logging.error(f"Decoded content exceeds size limit: {len(file_content)/1024/1024:.2f} MB")
                return None

            temp_path = os.path.join(self.temp_dir, attachment.file_name)
            with open(temp_path, "wb") as f:
                f.write(file_content)

            result = await self._upload_file(temp_path)
            if not result or "uri" not in result:
                logging.error(f"Upload failed: {result}")
                return None

            self._clean_up_uploaded_file(temp_path, result["uri"])
            return result["uri"]
        except Exception as e:
            logging.error(f"Error uploading file: {str(e)}", exc_info=True)
            return None

    async def _upload_file(self, file_path: str) -> Dict[str, Any]:
        """Upload a file manually using HTTP requests

        Args:
            file_path: Path to the file

        Returns:
            Upload result dictionary
        """
        file_name = os.path.basename(file_path)
        mime = magic.Magic(mime=True)
        mime_type = mime.from_file(file_path)

        api_key = self._get_api_key()
        email = self.config.get_setting("adapter", "adapter_email")
        upload_url = f"{self.zulip_site}/api/v1/user_uploads"
        auth = aiohttp.BasicAuth(email, api_key)

        try:
            async with aiohttp.ClientSession() as session:
                with open(file_path, "rb") as f:
                    form_data = aiohttp.FormData()
                    form_data.add_field("file", f, filename=file_name, content_type=mime_type)

                    async with session.post(upload_url, data=form_data, auth=auth) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logging.error(f"Upload failed with status {response.status}: {error_text}")
                            return {}

                        return await response.json()
        except Exception as e:
            logging.error(f"Error in manual upload: {e}", exc_info=True)
            return {}

    def _clean_up_uploaded_file(self, old_path: str, zulip_uri: str) -> None:
        """Clean up a file after it has been uploaded to Zulip

        Args:
            old_path: Path to the old file
            zulip_uri: Zulip URI of the uploaded file
        """
        file_extension = old_path.split(".")[-1]
        attachment_id = self._generate_attachment_id(zulip_uri)
        attachment_type = get_attachment_type_by_extension(file_extension)
        attachment_dir = os.path.join(self.download_dir, attachment_type, attachment_id)

        file_name = str(attachment_id)
        if "." in old_path:
            file_name += "." + file_extension

        create_attachment_dir(attachment_dir)
        move_attachment(old_path, os.path.join(attachment_dir, file_name))
