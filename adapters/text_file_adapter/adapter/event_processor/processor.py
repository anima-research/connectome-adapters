import asyncio
import json
import logging
import os
import pathlib
import shutil
import tempfile

from datetime import datetime
from enum import Enum
from pathlib import Path
from pydantic import BaseModel
from typing import Any, Dict, List
from uuid import uuid4

from adapters.text_file_adapter.adapter.event_processor.file_event_cache import FileEventCache
from adapters.text_file_adapter.adapter.event_processor.file_validator import FileValidator
from adapters.text_file_adapter.adapter.event_processor.outgoing_events import OutgoingEventBuilder
from core.utils.config import Config

class FileEventType(str, Enum):
    """Event types supported by the OutgoingEventProcessor"""
    VIEW = "view"
    READ = "read"
    CREATE = "create"
    DELETE = "delete"
    MOVE = "move"
    UPDATE = "update"
    INSERT = "insert"
    REPLACE = "replace"
    UNDO = "undo"

class Processor():
    """Processes events from socket.io"""

    def __init__(self, config: Config, file_event_cache: FileEventCache):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            file_event_cache: FileEventCache instance
        """
        self.config = config
        self.file_event_cache = file_event_cache
        self.base_dir = self.config.get_setting("adapter", "base_directory")
        self.allowed_directories = self.config.get_setting("adapter", "allowed_directories")
        self.max_file_size = self.config.get_setting(
            "adapter", "max_file_size"
        ) * 1024 * 1024

    async def process_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an event based on its type

        Args:
            data: The event data

        Returns:
            Dict[str, Any]: Dictionary containing the status and data fields if applicable
        """
        try:
            event_handlers = {
                FileEventType.VIEW: self._handle_view_event,
                FileEventType.READ: self._handle_read_event,
                FileEventType.CREATE: self._handle_create_event,
                FileEventType.DELETE: self._handle_delete_event,
                FileEventType.MOVE: self._handle_move_event,
                FileEventType.UPDATE: self._handle_update_event,
                FileEventType.INSERT: self._handle_insert_event,
                FileEventType.REPLACE: self._handle_replace_event,
                FileEventType.UNDO: self._handle_undo_event
            }
            outgoing_event = OutgoingEventBuilder(data).build()
            handler = event_handlers.get(outgoing_event.event_type)

            return await handler(outgoing_event.data)
        except Exception as e:
            logging.error(f"Error processing event: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_view_event(self, data: BaseModel) -> Dict[str, Any]:
        """List files and directories in a directory

        Args:
            data: data model containing:
                - path: Path to the directory to view

        Returns:
            Dictionary containing success status and file/directory listing
        """
        try:
            path = self._sanitize_path(data.path)
            if not os.path.isdir(path):
                logging.error(f"Path is not a directory: {path}")
                return {"request_completed": False}

            files = []
            directories = []

            for item in os.listdir(path):
                item_path = os.path.join(path, item)

                if os.path.isfile(item_path):
                    files.append(item)
                elif os.path.isdir(item_path):
                    directories.append(item)

            return {
                "request_completed": True,
                "directories": directories,
                "files": files
            }
        except Exception as e:
            logging.error(f"Error viewing directory: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_read_event(self, data: BaseModel) -> Dict[str, Any]:
        """Read a file's contents

        Args:
            data: data model containing:
                - path: Path to the file to read
                - line_range: (Optional) [start, end] line range to read

        Returns:
            Dictionary containing success status and file content
        """
        try:
            path = self._sanitize_path(data.path)
            validator = FileValidator(path, self.config)

            if not validator.validate():
                error_msg = " ".join(validator.errors)
                logging.error(f"File validation failed: {path}. {error_msg}")
                return {"request_completed": False}

            view_range = data.line_range
            with open(path, "r", encoding="utf-8") as file:
                if view_range:
                    content = "".join(file.readlines()[view_range[0]:view_range[1]])
                else:
                    content = file.read()

            return {"request_completed": True, "content": content}
        except Exception as e:
            logging.error(f"Error reading file: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_create_event(self, data: BaseModel) -> Dict[str, Any]:
        """Create a new file with content

        Args:
            data: data model containing:
                - path: Path to create the file
                - content: Content to write to the file

        Returns:
            Dictionary containing success status
        """
        try:
            path = self._sanitize_path(data.path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            await self.file_event_cache.record_create_event(path)

            with open(path, "w", encoding="utf-8") as file:
                file.write(data.content)

            return {"request_completed": True}
        except Exception as e:
            logging.error(f"Error creating file: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_delete_event(self, data: BaseModel) -> Dict[str, Any]:
        """Delete a file

        Args:
            data: data model containing:
                - path: Path to the file to delete

        Returns:
            Dictionary containing success status
        """
        try:
            path = self._sanitize_path(data.path)
            self._check_if_path_exists(path)
            await self.file_event_cache.record_delete_event(path)
            os.remove(path)

            return {"request_completed": True}
        except Exception as e:
            logging.error(f"Error deleting file: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_move_event(self, data: BaseModel) -> Dict[str, Any]:
        """Move a file to a new location

        Args:
            data: data model containing:
                - source_path: Path to the file to move
                - destination_path: New path for the file

        Returns:
            Dictionary containing success status
        """
        try:
            source_path = self._sanitize_path(data.source_path)
            self._check_if_path_exists(source_path)

            destination_path = self._sanitize_path(data.destination_path)
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)

            await self.file_event_cache.record_move_event(source_path, destination_path)
            shutil.move(source_path, destination_path)
            logging.warning(f"Moved file from {source_path} to {destination_path}. Cannot be undone.")

            return {"request_completed": True}
        except Exception as e:
            logging.error(f"Error moving file: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_update_event(self, data: BaseModel) -> Dict[str, Any]:
        """Update a file's entire content

        Args:
            data: data model containing:
                - path: Path to the file to update
                - content: New content for the file

        Returns:
            Dictionary containing success status
        """
        try:
            path = self._sanitize_path(data.path)
            self._check_if_path_exists(path)
            await self.file_event_cache.record_update_event(path)

            with open(path, "w", encoding="utf-8") as file:
                file.write(data.content)

            return {"request_completed": True}
        except Exception as e:
            logging.error(f"Error updating file: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_insert_event(self, data: BaseModel) -> Dict[str, Any]:
        """Insert content at a specific line in a file

        Args:
            data: data model containing:
                - path: Path to the file
                - line: Line number to insert after (0 for beginning of file)
                - content: Content to insert

        Returns:
            Dictionary containing success status
        """
        try:
            path = self._sanitize_path(data.path)
            self._check_if_path_exists(path)
            await self.file_event_cache.record_update_event(path)

            with open(path, "r", encoding="utf-8") as file:
                lines = file.readlines()

            line_number = int(data.line)
            if line_number == 0:
                lines.insert(0, data.content)
            elif line_number > len(lines):
                lines.append(data.content)
            else:
                lines.insert(line_number, data.content)

            with open(path, "w", encoding="utf-8") as file:
                file.writelines(lines)

            return {"request_completed": True}
        except Exception as e:
            logging.error(f"Error inserting into file: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_replace_event(self, data: BaseModel) -> Dict[str, Any]:
        """Replace text in a file

        Args:
            data: data model containing:
                - path: Path to the file
                - old_string: Text to replace
                - new_string: Replacement text

        Returns:
            Dictionary containing success status
        """
        try:
            path = self._sanitize_path(data.path)
            self._check_if_path_exists(path)
            await self.file_event_cache.record_update_event(path)

            with open(path, "r", encoding="utf-8") as file:
                content = file.read()

            new_content = content.replace(data.old_string, data.new_string)
            with open(path, "w", encoding="utf-8") as file:
                file.write(new_content)

            return {"request_completed": True}
        except Exception as e:
            logging.error(f"Error replacing text in file: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_undo_event(self, data: BaseModel) -> Dict[str, Any]:
        """Undo the last change to a file

        Args:
            data: data model containing:
                - path: Path to the file

        Returns:
            Dictionary containing success status
        """
        try:
            path = self._sanitize_path(data.path)
            restored = await self.file_event_cache.undo_recorded_event(path)

            if restored:
                return {"request_completed": True}
        except Exception as e:
            logging.error(f"Error undoing file changes: {e}", exc_info=True)

        return {"request_completed": False}

    def _sanitize_path(self, path: str) -> str:
        """Sanitize a path to prevent directory traversal"""
        if not os.path.isabs(path):
            return os.path.abspath(os.path.join(self.base_dir, path))

        abs_path = os.path.abspath(path)

        if not any(abs_path.startswith(allowed_dir) for allowed_dir in self.allowed_directories):
            raise ValueError(f"Access denied to path outside allowed directories: {abs_path}")

        return abs_path

    def _check_if_path_exists(self, path: str) -> bool:
        """Check if a path exists

        Args:
            path: The path to check if it exists

        Returns:
            True if the path exists

        Raises:
            ValueError: If the path does not exist
        """
        if not os.path.exists(path):
            raise ValueError(f"Path does not exist: {path}")

        return True
