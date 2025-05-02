import asyncio
import logging
import os
import shutil
import time
import uuid

from typing import Any, Dict, List
from core.utils.config import Config

class FileEventCache:
    """Cache for file events with undo functionality"""

    def __init__(self, config: Config, start_maintenance: bool = False):
        """Initialize the event cache

        Args:
            config: Configuration instance
        """
        self.config = config
        self.start_maintenance = start_maintenance
        self.event_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.backup_dir = self.config.get_setting("adapter", "backup_directory")
        self.event_ttl = self.config.get_setting("adapter", "event_ttl_hours")
        self.cleanup_interval = self.config.get_setting("adapter", "cleanup_interval_hours")
        self.max_events_per_file = self.config.get_setting("adapter", "max_events_per_file")
        self.cleanup_task = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the cleanup task"""
        if self.start_maintenance:
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            logging.info("Started file event cache cleanup task")

        if self.backup_dir:
            os.makedirs(self.backup_dir, exist_ok=True)

    async def stop(self):
        """Stop the cleanup task"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            logging.info("Stopped file event cache cleanup task")

        if self.backup_dir and os.path.exists(self.backup_dir):
            logging.info(f"Removing backup directory: {self.backup_dir}")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: shutil.rmtree(self.backup_dir, ignore_errors=True)
            )

    async def record_create_event(self, file_path: str) -> None:
        """Record a file creation event for undo purposes

        Args:
            file_path: Path to the created file
        """
        async with self._lock:
            await self._add_event_to_cache(
                file_path,
                {
                    "timestamp": time.time(),
                    "action": "delete"
                }
            )

    async def record_update_event(self, file_path: str) -> None:
        """Record a file update event

        Args:
            file_path: Path to the updated file
        """
        async with self._lock:
            backup = await self._create_backup(file_path)

            if not backup:
                raise Exception(f"Failed to create backup for {file_path}")

            await self._add_event_to_cache(
                file_path,
                {
                    "action": "update",
                    "timestamp": time.time(),
                    "backup_info": backup
                }
            )

    async def record_delete_event(self, file_path: str) -> None:
        """Record a file deletion event

        Args:
            file_path: Path to the deleted file
        """
        async with self._lock:
            backup = await self._create_backup(file_path)

            if not backup:
                raise Exception(f"Failed to create backup for {file_path}")

            await self._add_event_to_cache(
                file_path,
                {
                    "action": "create",
                    "timestamp": time.time(),
                    "backup_info": backup
                }
            )

    async def record_move_event(self, old_path: str, new_path: str) -> None:
        """Record a file move event

        Args:
            old_path: Path to the original file
            new_path: Path to the new file
        """
        async with self._lock:
            if old_path in self.event_cache:
                del self.event_cache[old_path]

    async def undo_recorded_event(self, file_path: str) -> bool:
        """Undo the last recorded event for a file

        Args:
            file_path: Path to the file

        Returns:
            True if the event was undone, False otherwise
        """
        async with self._lock:
            if file_path not in self.event_cache or not self.event_cache[file_path]:
                logging.warning(f"No events recorded for {file_path}")
                return False

            event = self.event_cache[file_path].pop()
            if not self.event_cache[file_path]:
                del self.event_cache[file_path]

            if event["action"] in ["create", "update"]:
                result = await self._restore_from_backup(event["backup_info"])
                await self._cleanup_backup(event["backup_info"])
                return result

            if event["action"] == "delete":
                try:
                    os.remove(file_path)
                    return True
                except Exception as e:
                    return False

            return False

    async def _cleanup_loop(self):
        """Background loop for periodic cleanup"""
        interval_seconds = self.cleanup_interval * 3600

        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._cleanup_expired_events()
                logging.debug(f"Cleaned up expired file events")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in file event cache cleanup task: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _cleanup_expired_events(self) -> None:
        """Clean up expired events and their backups"""
        async with self._lock:
            expiration_time = time.time() - (self.event_ttl * 3600) # Convert to seconds

            for file_path in list(self.event_cache.keys()):
                events = self.event_cache[file_path]
                expired_events = [
                    event for event in events if event["timestamp"] < expiration_time
                ]

                for event in expired_events:
                    if "backup_info" in event:
                        await self._cleanup_backup(event["backup_info"])

                self.event_cache[file_path] = [
                    event for event in events if event["timestamp"] >= expiration_time
                ]

                if not self.event_cache[file_path]:
                    del self.event_cache[file_path]

    async def _add_event_to_cache(self, file_path: str, event_info: Dict[str, Any]) -> None:
        """Add an event to the cache, respecting the maximum events per file

        Args:
            file_path: Path to the file
            event_info: Event information to add
        """
        if file_path not in self.event_cache:
            self.event_cache[file_path] = []

        self.event_cache[file_path].append(event_info)

        if len(self.event_cache[file_path]) > self.max_events_per_file:
            oldest_event = self.event_cache[file_path][0]

            if "backup_info" in oldest_event:
                await self._cleanup_backup(oldest_event["backup_info"])

            self.event_cache[file_path] = self.event_cache[file_path][1:]

    async def _create_backup(self, file_path: str) -> Dict[str, Any]:
        """Create a backup of a file

        Args:
            file_path: Path to the file to backup

        Returns:
            Backup information
        """
        try:
            backup_id = str(uuid.uuid4())
            backup_dir = os.path.join(self.backup_dir, f"{backup_id}")
            os.makedirs(backup_dir, exist_ok=True)

            backup_file = os.path.join(backup_dir, "original_content.bak")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: shutil.copy2(file_path, backup_file))

            return {
                "original_file_path": file_path,
                "backup_file_path": backup_file,
                "backup_id": backup_id
            }
        except Exception as e:
            logging.error(f"Error creating backup for {file_path}: {e}", exc_info=True)
            return {}

    async def _cleanup_backup(self, backup_info: Dict[str, Any]) -> None:
        """Clean up a backup

        Args:
            backup_info: Backup information
        """
        try:
            if os.path.exists(backup_info["backup_file_path"]):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: shutil.rmtree(
                        os.path.dirname(backup_info["backup_file_path"])
                    )
                )
        except Exception as e:
            logging.error(f"Error cleaning up backup {backup_info['backup_id']}: {e}", exc_info=True)

    async def _restore_from_backup(self, backup_info: Dict[str, Any]) -> bool:
        """Restore a file from its backup

        Args:
            backup_info: Backup information

        Returns:
            True if restoration was successful, False otherwise
        """
        try:
            os.makedirs(os.path.dirname(backup_info["original_file_path"]), exist_ok=True)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: shutil.copy2(backup_info["backup_file_path"], backup_info["original_file_path"])
            )
            return True
        except Exception as e:
            logging.error(f"Error restoring from backup {backup_info['backup_id']}: {e}", exc_info=True)
            return False
