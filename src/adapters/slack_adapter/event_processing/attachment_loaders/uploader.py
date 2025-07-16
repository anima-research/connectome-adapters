import base64
import logging
import os
import shutil

from typing import Any, List
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.attachment_loading import (
    create_attachment_dir,
    get_attachment_type_by_extension,
    move_attachment
)
from src.core.utils.config import Config

class Uploader():
    """Prepares files for upload to Slack"""

    def __init__(self, config: Config, client: Any):
        """Initialize with a Slack client

        Args:
            config: Config instance
            client: Slack client
        """
        self.config = config
        self.client = client
        self.rate_limiter = RateLimiter(self.config)
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.temp_dir = os.path.join(self.download_dir, "tmp_uploads")
        self.max_file_size = self.config.get_setting("attachments", "max_file_size_mb") * 1024 * 1024

        os.makedirs(self.temp_dir, exist_ok=True)

    def __del__(self):
        """Cleanup the temporary directory when object is garbage collected"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logging.info(f"Removed temporary upload directory: {self.temp_dir}")
        except Exception as e:
            logging.error(f"Error removing temporary directory: {e}")

    async def upload_attachments(self, conversation_info: Any, data: Any) -> None:
        """Upload a file to Slack

        Args:
            conversation_info: Conversation info
            data: Event data containing attachments
        """
        for attachment in data.attachments:
            try:
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

                await self.rate_limiter.limit_request("message", data.conversation_id)

                upload_params = {
                    "file": temp_path,
                    "channel": conversation_info.platform_conversation_id.split("/")[-1]
                }
                if data.thread_id:
                    upload_params["thread_ts"] = data.thread_id

                response = await self.client.files_upload_v2(**upload_params)
                file_id = response.get("file", {}).get("id", None)

                if file_id:
                    self._clean_up_uploaded_file(temp_path, file_id)
            except Exception as e:
                logging.error(f"Error uploading file: {str(e)}", exc_info=True)

    def _clean_up_uploaded_file(self, old_path: str, slack_file_id: str) -> None:
        """Clean up a file after it has been uploaded to Slack

        Args:
            old_path: Path to the old file
            slack_file_id: Slack file ID of the uploaded file
        """
        file_extension = old_path.split(".")

        if len(file_extension) > 1:
            file_extension = file_extension[-1]
        else:
            file_extension = ""

        attachment_type = get_attachment_type_by_extension(file_extension)
        attachment_dir = os.path.join(
            self.download_dir, attachment_type, slack_file_id
        )
        file_path = os.path.join(
            attachment_dir,
            slack_file_id if not file_extension else f"{slack_file_id}.{file_extension}"
        )

        create_attachment_dir(attachment_dir)
        move_attachment(old_path, file_path)
