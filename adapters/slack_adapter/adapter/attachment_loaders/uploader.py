import logging
import os

from typing import Any, Dict, List, Optional
from core.rate_limiter.rate_limiter import RateLimiter
from core.utils.attachment_loading import (
    create_attachment_dir,
    delete_empty_directory,
    get_attachment_type_by_extension,
    move_attachment
)
from core.utils.config import Config

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
        self.max_file_size = self.config.get_setting("attachments", "max_file_size_mb") * 1024 * 1024

    async def upload_attachments(self,
                                 conversation_id: str,
                                 attachments: List[Dict[str, Any]]) -> None:
        """Upload a file to Slack

        Args:
            conversation_id: Conversation ID to share the file in
            attachments: List of attachment details (json)
        """
        for attachment in attachments:
            try:
                if not os.path.exists(attachment["file_path"]):
                    logging.error(f"File not found: {attachment['file_path']}")
                    continue

                if attachment["size"] > self.max_file_size:
                    logging.error(f"File exceeds Slack's size limit: {attachment['size']/1024/1024:.2f} MB "
                                  f"(max {self.max_file_size/1024/1024:.2f} MB)")
                    continue

                await self.rate_limiter.limit_request("message", conversation_id)
                response = await self.client.files_upload_v2(
                    file=attachment["file_path"],
                    channel=conversation_id.split("/")[-1]
                )

                file_id = response.get("file", {}).get("id", None)
                if file_id:
                    self._clean_up_uploaded_file(attachment["file_path"], file_id)
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
        delete_empty_directory(old_path)
