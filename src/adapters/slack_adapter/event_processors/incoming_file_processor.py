import asyncio
import logging
import time

from typing import Any, Dict
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.config import Config

class IncomingFileProcessor:
    def __init__(self, config: Config, client: Any, adapter: Any):
        """Initialize the Slack IncomingFileProcessor

        Args:
            config: Config instance
            client: Slack client instance
            adapter: Slack adapter instance
        """
        self.config = config
        self.client = client
        self.adapter = adapter
        self.rate_limiter = RateLimiter.get_instance(config)
        self.status_cache = {}
        self.processing_tasks = {}

    async def schedule_file_processing(self, event: Dict[str, Any]) -> None:
        """Schedule a file for processing with appropriate strategy

        Args:
            event: Slack event object
        """
        slack_media = event.get("subtype", None) in ["slack_audio", "slack_video"]

        for file in event.get("files", []):
            file_id = file.get("id", None)

            if not file_id or file_id in self.processing_tasks:
                return

            task = asyncio.create_task(
                self._process_file_with_retries(
                    file_id,
                    file,
                    event,
                    initial_delay=5 if slack_media else 1,
                    max_retries=10 if slack_media else 5,
                    backoff_factor=1.5 if slack_media else 2
                )
            )
            task.add_done_callback(
                lambda _: self.processing_tasks.pop(file_id, None)
            )
            self.processing_tasks[file_id] = (task, event)

    async def _process_file_with_retries(self,
                                         file_id,
                                         file_info,
                                         event,
                                         initial_delay,
                                         max_retries,
                                         backoff_factor) -> None:
        """Process a file with adaptive retries and rate limiting

        Args:
            file_id: File ID
            file_info: File info
            event: Slack event object
            initial_delay: Initial delay
            max_retries: Maximum number of retries
            backoff_factor: Backoff factor
        """
        team_id = event.get("team", None)
        channel_id = event.get("channel", None)
        delay = initial_delay

        for _ in range(max_retries):
            try:
                await asyncio.sleep(delay)
                updated_info = await self._get_file_status(
                    file_id, f"{team_id}/{channel_id}"
                )

                if self._is_file_ready(updated_info):
                    await self._process_file(file_id)
                    return

                delay = min(30, delay * backoff_factor)  # Cap at 30 seconds
            except Exception as e:
                logging.error(f"Error processing file {file_id}: {e}")
                delay = min(30, delay * backoff_factor)

        logging.warning(f"File {file_id} not ready after {max_retries} attempts, processing anyway")

        try:
            await self._process_file(file_id)
        except Exception as e:
            logging.error(f"Error processing file after max retries: {e}")

    async def _get_file_status(self, file_id: str, conversation_id: str) -> Dict[str, Any]:
        """Get file status with rate limiting and caching

        Args:
            file_id: File ID
            conversation_id: Conversation ID

        Returns:
            File info
        """
        cache_entry = self.status_cache.get(file_id, {})
        now = time.time()
        if cache_entry and now - cache_entry["timestamp"] < 5:
            return cache_entry["info"]

        await self.rate_limiter.limit_request("file_info", conversation_id)
        response = await self.client.files_info(file=file_id)
        self.status_cache[file_id] = {
            "info": response["file"],
            "timestamp": now
        }

        return self.status_cache[file_id]["info"]

    def _is_file_ready(self, file_info: Dict[str, Any]) -> bool:
        """Check if a file is ready to download

        Args:
            file_info: File info

        Returns:
            True if file is ready, False otherwise
        """
        if not file_info.get("url_private_download", None) \
           and not file_info.get("url_private", None):
            return False

        subtype = file_info.get("subtype", None)
        if subtype in ["slack_audio", "slack_video"]:
            transcription = file_info.get("transcription", {})
            if transcription.get("status") == "processing":
                if subtype == "slack_audio" and not file_info.get("aac", None):
                    return False
                if subtype == "slack_video" and not file_info.get("mp4", None):
                    return False

        mode = file_info.get("mode", None)
        filetype = file_info.get("filetype", None)

        if (mode in ["quip", "list"] or
            filetype in ["quip", "list"]) and file_info.get("size", 0) == 0:
            return True

        return True

    async def _process_file(self, file_id: str) -> None:
        """Download file and process the message

        Args:
            file_id: File ID
        """
        _, event = self.processing_tasks[file_id]

        await self.adapter.process_incoming_event({
            "type": "message",
            "event": event
        })

        if file_id in self.status_cache:
            del self.status_cache[file_id]
