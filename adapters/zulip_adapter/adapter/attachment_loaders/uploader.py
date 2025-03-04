import asyncio
import logging
import os
import mimetypes
import aiohttp

from typing import Dict, Any, Optional
from adapters.zulip_adapter.adapter.attachment_loaders.base_loader import BaseLoader
from core.utils.attachment_loading import (
    create_attachment_dir,
    delete_empty_directory,
    get_attachment_type_by_extension,
    move_attachment
)
from core.utils.config import Config

class Uploader(BaseLoader):
    """Handles efficient file uploads to Zulip"""

    def __init__(self, config: Config, client: Any):
        """Initialize with Config instance and Zulip client

        Args:
            config: Config instance
            client: Zulip client
        """
        super().__init__(config, client)

    async def upload_attachment(self, attachment: Dict[str, Any]) -> Optional[str]:
        """Upload a file to Zulip

        Args:
            attachment: Attachment details (json)

        Returns:
            Dictionary with attachment metadata or {} if error
        """
        try:
            if not os.path.exists(attachment["file_path"]):
                logging.error(f"File not found: {attachment['file_path']}")
                return None

            if attachment["size"] > self.max_file_size:
                logging.error(f"File exceeds Zulip's size limit: {attachment['size']/1024/1024:.2f} MB "
                              f"(max {self.max_file_size/1024/1024:.2f} MB)")
                return None

            result = await self._upload_file(attachment["file_path"])
            if not result or "uri" not in result:
                logging.error(f"Upload failed: {result}")
                return None

            self._clean_up_uploaded_file(attachment["file_path"], result["uri"])
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
        mime_type = self._get_mime_type(file_path)

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

    def _get_mime_type(self, file_path: str) -> str:
        """Get the MIME type of a file

        Args:
            file_path: Path to the file

        Returns:
            MIME type string
        """
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            return "application/octet-stream"
        return mime_type

    def _clean_up_uploaded_file(self, old_path: str, zulip_uri: str) -> None:
        """Clean up a file after it has been uploaded to Zulip

        Args:
            old_path: Path to the old file
            zulip_uri: Zulip URI of the uploaded file
        """
        file_extension = old_path.split(".")[-1]

        attachment_id = self._generate_attachment_id(zulip_uri)
        attachment_type = get_attachment_type_by_extension(file_extension)

        attachment_dir = os.path.join(
            self.download_dir, attachment_type, attachment_id
        )
        file_path = os.path.join(
            attachment_dir, f"{attachment_id}.{file_extension}"
        )

        create_attachment_dir(attachment_dir)
        move_attachment(old_path, file_path)
        delete_empty_directory(old_path)
