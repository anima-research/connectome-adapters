import asyncio
import json
import logging
import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, Any

from core.utils.config import Config

@dataclass
class CachedAttachment:
    """Information about a cached Telegram attachment"""
    attachment_id: str
    attachment_type: str
    created_at: datetime = field(default_factory=datetime.now)
    file_extension: Optional[str] = None
    size: Optional[int] = None
    conversations: Set[str] = field(default_factory=set)  # Set of conversation IDs where this appears

    @property
    def file_path(self) -> str:
        """Get the full path to the attachment file"""
        if self.file_extension:
            return os.path.join(
                self.attachment_type,
                self.attachment_id,
                f"{self.attachment_id}.{self.file_extension}"
            )
        return os.path.join(self.attachment_type, self.attachment_id, self.attachment_id)

    @property
    def metadata_path(self) -> str:
        """Get the full path to the attachment file"""
        return os.path.join(self.attachment_type, self.attachment_id, f"{self.attachment_id}.json")

class AttachmentCache:
    """Tracks and manages information about Telegram attachments"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the attachment cache

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        self.config = config
        self.attachments: Dict[str, CachedAttachment] = {}  # attachment_id -> CachedAttachment
        self._lock = asyncio.Lock()
        self.storage_dir = self.config.get_setting("attachments", "storage_dir")
        self.max_age_days = self.config.get_setting("attachments", "max_age_days")
        self.max_total_attachments = self.config.get_setting("attachments", "max_total_attachments")
        self.cleanup_interval_hours = self.config.get_setting("attachments", "cleanup_interval_hours")
        self.maintenance_task = asyncio.create_task(self._maintenance_loop()) if start_maintenance else None

        self._upload_existing_attachments()

    def __del__(self):
        """Cleanup when object is garbage collected"""
        if self.maintenance_task:
            if not self.maintenance_task.done() and not self.maintenance_task.cancelled():
                self.maintenance_task.cancel()
                logging.info("Cache maintenance task cancelled during cleanup")

    def _upload_existing_attachments(self) -> None:
        """Load existing attachments from storage directory"""
        if not os.path.exists(self.storage_dir):
            return

        try:
            for attachment_type in os.listdir(self.storage_dir):
                type_dir = os.path.join(self.storage_dir, attachment_type)
                if not os.path.isdir(type_dir):
                    continue

                for filename in os.listdir(type_dir):
                    metadata_path = os.path.join(type_dir, filename, f"{filename}.json")
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)

                    cached_attachment = CachedAttachment(
                        attachment_id=metadata.get("attachment_id"),
                        attachment_type=metadata.get("attachment_type"),
                        created_at=datetime.fromisoformat(
                            metadata.get("created_at", datetime.now().isoformat())
                        ),
                        file_extension=metadata.get("file_extension"),
                        size=metadata.get("size"),
                    )

                    cached_attachment.conversations = set()
                    self.attachments[metadata.get("attachment_id")] = cached_attachment
        except Exception as e:
            logging.error(f"Error loading attachment from {self.storage_dir}: {e}")

    async def _maintenance_loop(self) -> None:
        """Periodically clean up old attachments"""
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval_hours * 3600)
                await self._enforce_age_limit()
                await self._enforce_total_limit()

                logging.info(f"Attachment cache maintenance completed")
        except asyncio.CancelledError:
            logging.info("Attachment cache maintenance task cancelled")
        except Exception as e:
            logging.error(f"Error in attachment cache maintenance: {e}")

    async def _enforce_age_limit(self) -> None:
        """Remove attachments older than max age"""
        max_age = timedelta(days=self.max_age_days)
        cutoff_date = datetime.now() - max_age

        async with self._lock:
            to_remove = []

            for attachment_id, attachment in self.attachments.items():
                if attachment.created_at < cutoff_date:
                    to_remove.append(attachment_id)

            for attachment_id in to_remove:
                await self.remove_attachment(attachment_id)

            logging.info(f"Removed {len(to_remove)} attachments due to age limit")

    async def _enforce_total_limit(self) -> None:
        """Ensure total attachments don't exceed limit"""
        if len(self.attachments) <= self.max_total_attachments:
            return

        to_remove_count = len(self.attachments) - self.max_total_attachments

        async with self._lock:
            sorted_attachments = sorted(
                self.attachments.items(),
                key=lambda x: x[1].created_at
            )

            for attachment_id, _ in sorted_attachments[:to_remove_count]:
                await self.remove_attachment(attachment_id)

            logging.info(f"Removed attachments due to total limit")

    def get_attachment(self, attachment_id: str) -> Optional[CachedAttachment]:
        """Get an attachment from the cache

        Args:
            attachment_id: Attachment ID

        Returns:
            CachedAttachment or None if not found
        """
        return self.attachments.get(attachment_id, {})

    async def add_attachment(self, conversation_id: str, attachment_info: Dict[str, Any]) -> None:
        """Add an attachment to the cache

        Args:
            conversation_id: Conversation ID
            attachment_info: Attachment info
        """
        async with self._lock:
            if attachment_info["attachment_id"] not in self.attachments:
                self.attachments[attachment_info["attachment_id"]] = CachedAttachment(
                    attachment_id=attachment_info["attachment_id"],
                    attachment_type=attachment_info["attachment_type"],
                    created_at=attachment_info["created_at"],
                    file_extension=attachment_info["file_extension"],
                    size=attachment_info["size"]
                )

            self.attachments[attachment_info["attachment_id"]].conversations.add(conversation_id)
            return self.attachments[attachment_info["attachment_id"]]

    async def remove_attachment(self, attachment_id: str) -> None:
        """Remove an attachment from the cache

        Args:
            attachment_id: Attachment ID
        """
        async with self._lock:
            if attachment_id not in self.attachments:
                return

            attachment = self.attachments[attachment_id]

            try:
                file_path = os.path.join(self.storage_dir, attachment.file_path)
                if os.path.exists(file_path):
                    os.remove(file_path)

                metadata_path = os.path.join(self.storage_dir, attachment.metadata_path)
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)

                parent_dir = os.path.dirname(file_path)
                if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            except Exception as e:
                logging.error(f"Error deleting attachment files: {e}")

            del self.attachments[attachment_id]
            logging.info(f"Removed attachment {attachment_id} from cache")
