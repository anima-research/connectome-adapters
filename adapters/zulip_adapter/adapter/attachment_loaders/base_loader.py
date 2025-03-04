import hashlib

from typing import Any
from core.utils.config import Config

class BaseLoader:
    """Basic attachment loader for Zulip"""

    def __init__(self, config: Config, client: Any):
        """Initialize with a Zulip client

        Args:
            config: Config instance
            client: Zulip client instance
        """
        self.config = config
        self.client = client
        self.download_dir = self.config.get_setting("attachments", "storage_dir")
        self.large_file_threshold = self.config.get_setting(
            "attachments", "large_file_threshold_mb"
        ) * 1024 * 1024  # Convert to bytes
        self.max_file_size = self.config.get_setting(
            "attachments", "max_file_size_mb"
        ) * 1024 * 1024  # Convert to bytes
        self.zulip_site = self.config.get_setting("adapter", "site", "").rstrip("/")

    def _generate_attachment_id(self, file_path: str) -> str:
        """Generate a unique ID for an attachment based on its path

        Args:
            file_path: The file path from the Zulip message

        Returns:
            A unique identifier for the attachment
        """
        path_parts = file_path.split("/")
        if len(path_parts) >= 5:
            return path_parts[-2]
        return hashlib.md5(file_path.encode()).hexdigest()

    def _get_api_key(self) -> str:
        """Get the API key from the client or config

        Returns:
            API key string
        """
        if hasattr(self.client, "api_key"):
            return self.client.api_key
        return None
