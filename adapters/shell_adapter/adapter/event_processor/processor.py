import asyncio
import os
import logging
import platform
import shutil
import sys
import subprocess

from enum import Enum
from pydantic import BaseModel
from typing import Any, Dict

from adapters.shell_adapter.adapter.event_processor.outgoing_events import OutgoingEventBuilder
from adapters.shell_adapter.adapter.session.command_executor import CommandExecutor
from adapters.shell_adapter.adapter.session.manager import Manager
from adapters.shell_adapter.adapter.shell.metadata_fetcher import MetadataFetcher

from core.utils.config import Config

class FileEventType(str, Enum):
    """Event types supported by the OutgoingEventProcessor"""
    OPEN_SESSION = "open_session"
    CLOSE_SESSION = "close_session"
    EXECUTE_COMMAND = "execute_command"
    SHELL_METADATA = "shell_metadata"

class Processor():
    """Processes events from socket.io"""

    def __init__(self, config: Config, session_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            session_manager: SessionManager instance
        """
        self.config = config
        self.session_manager = session_manager
        self.outgoing_event_builder = OutgoingEventBuilder()
        self.metadata_fetcher = MetadataFetcher(config)

    async def process_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an event based on its type

        Args:
            data: The event data

        Returns:
            Dict[str, Any]: Dictionary containing the status and data fields if applicable
        """
        try:
            event_handlers = {
                FileEventType.OPEN_SESSION: self._handle_open_session_event,
                FileEventType.CLOSE_SESSION: self._handle_close_session_event,
                FileEventType.EXECUTE_COMMAND: self._handle_execute_command_event,
                FileEventType.SHELL_METADATA: self._handle_shell_metadata_event,
            }

            outgoing_event = self.outgoing_event_builder.build(data)
            handler = event_handlers.get(outgoing_event.event_type)

            return await handler(outgoing_event.data)
        except Exception as e:
            logging.error(f"Error processing event: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_open_session_event(self, _: BaseModel) -> Dict[str, Any]:
        """Open a new shell session

        Returns:
            Dictionary containing success status
        """
        try:
            session_id = await self.session_manager.open_session()
            return {"request_completed": True, "session_id": session_id}
        except Exception as e:
            logging.error(f"Error opening session: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_close_session_event(self, data: BaseModel) -> Dict[str, Any]:
        """Close the current shell session

        Args:
            data: data model containing:
                - session_id: The ID of the session to close

        Returns:
            Dictionary containing success status
        """
        try:
            await self.session_manager.close_session(data.session_id)
            return {"request_completed": True}
        except Exception as e:
            logging.error(f"Error closing session: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_execute_command_event(self, data: BaseModel) -> Dict[str, Any]:
        """Execute a command

        Args:
            data: data model containing:
                - command: The command to execute
                - session_id: The ID of the session to execute the command in or None

        Returns:
            Dictionary containing success status
        """
        try:
            session_id = data.session_id
            if not session_id:
                session_id = await self.session_manager.open_session()

            result = await self.session_manager.run_command(session_id, data.command)

            if not data.session_id:
                await self.session_manager.close_session(session_id)

            return {"request_completed": True, "metadata": result}
        except Exception as e:
            logging.error(f"Error executing command: {e}", exc_info=True)
            return {"request_completed": False}

    async def _handle_shell_metadata_event(self, _: BaseModel) -> Dict[str, Any]:
        """Get metadata about the shell

        Returns:
            Dictionary containing success status and shell metadata
        """
        try:
            return {
                "request_completed": True,
                "metadata": self.metadata_fetcher.fetch()
            }
        except Exception as e:
            logging.error(f"Error getting shell metadata: {e}", exc_info=True)
            return {"request_completed": False}
