import asyncio
import base64
import hashlib
import os

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.core.conversation.base_data_classes import BaseConversationInfo, ConversationDelta

from src.core.cache.message_cache import MessageCache, CachedMessage
from src.core.cache.attachment_cache import AttachmentCache
from src.core.conversation.base_data_classes import BaseConversationInfo, UserInfo, ThreadInfo
from src.core.utils.config import Config

class BaseManager(ABC):
    """Tracks and manages information about a conversations"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the conversation manager

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        self.config = config
        self.adapter_type = config.get_setting("adapter", "adapter_type")
        self.conversations: Dict[str, BaseConversationInfo] = {}
        self._lock = asyncio.Lock()
        self.message_cache = MessageCache(config, start_maintenance)
        self.attachment_cache = AttachmentCache(config, start_maintenance)
        self.message_builder = None # set by child class
        self.thread_handler = None # set by child class

    async def conversation_exists(self, event: Any) -> bool:
        """Check if a conversation exists for a given event

        Args:
            event: The platform event to check

        Returns:
            True if the conversation exists, False otherwise
        """
        platform_conversation_id = await self._get_platform_conversation_id(event)

        if not platform_conversation_id:
            return False

        return self._generate_deterministic_conversation_id(platform_conversation_id) in self.conversations

    def get_conversation(self, conversation_id: str) -> Optional[BaseConversationInfo]:
        """Get the conversation info for a given conversation ID

        Args:
            conversation_id: The ID of the conversation to get info for

        Returns:
            The conversation info for the given conversation ID, or None if it doesn't exist
        """
        return self.conversations.get(conversation_id, None)

    def get_conversation_cache(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get the conversation cache for a given conversation ID

        Args:
            conversation_id: The ID of the conversation to get info for

        Returns:
            The conversation cache for the given conversation ID, or None if it doesn't exist
        """
        result = []

        for msg in self.message_cache.messages.get(conversation_id, {}).values():
            if not msg.text and not msg.attachments:
                continue

            msg_dict = msg.cache_to_dict().copy()
            msg_dict["attachments"] = []
            msg_dict["mentions"] = []

            for attachment_id in msg.attachments:
                cached_attachment = self.attachment_cache.get_attachment(attachment_id)
                if cached_attachment:
                    msg_dict["attachments"].append({
                        "attachment_id": cached_attachment.attachment_id,
                        "filename": cached_attachment.filename,
                        "content_type": cached_attachment.content_type,
                        "content": None,
                        "size": cached_attachment.size,
                        "processable": cached_attachment.processable,
                        "url": cached_attachment.url
                    })

            result.append(msg_dict)

        return result

    def get_conversation_member(self, conversation_id: str, user_id: str) -> Optional[UserInfo]:
        """Get the member info for a given conversation and user ID

        Args:
            conversation_id: The ID of the conversation to get member info for
            user_id: The ID of the user to get info for

        Returns:
            The member info for the given conversation and user ID, or None if it doesn't exist
        """
        conversation = self.get_conversation(conversation_id)

        if not conversation:
            return None

        return conversation.known_members.get(user_id, None)

    async def add_to_conversation(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new conversation or add a message to an existing conversation

        Args:
            event: Event object that should contain the following keys:
                - message: Message object (type depends on the adapter)
                - attachments: Optional attachment information [Dict[str, Any]]
                - user: Optional user object (depends on the adapter)

        Returns:
            Dictionary with delta information
        """
        message = event.get("message", None)
        attachments = event.get("attachments", [])

        async with self._lock:
            if not message:
                return {}

            conversation_info = await self._get_or_create_conversation_info(event)
            if not conversation_info:
                return {}

            cached_msg = await self._create_message(
                message,
                conversation_info,
                await self._get_user_info(event, conversation_info),
                await self.thread_handler.add_thread_info(message, conversation_info)
            )

            attachments = await self._update_attachment(conversation_info, attachments)
            for attachment in attachments:
                cached_msg.attachments.add(attachment["attachment_id"])

            if not conversation_info.conversation_name:
                await self._update_conversation_name(event, conversation_info)

            delta = self._create_conversation_delta(event, conversation_info)
            delta.message_id = cached_msg.message_id
            mentions = self._get_mentions(delta, cached_msg, message)

            await self._update_delta_list(
                conversation_id=conversation_info.conversation_id,
                delta=delta,
                list_to_update="added_messages",
                cached_msg=cached_msg,
                attachments=attachments,
                mentions=mentions
            )

            return delta.to_dict()

    async def update_conversation(self, event: Any) -> Dict[str, Any]:
        """Update conversation information based on a received event

        Args:
            event: Event object that should contain the following keys:
                - event_type: Type of event
                - message: Message object
                - attachments: Optional attachment information (depends on the adapter)

        Returns:
            Dictionary with delta information
        """
        message = event.get("message", None)

        async with self._lock:
            if not message:
                return {}

            conversation_id = await self._get_conversation_id_from_update(message)
            if not conversation_id or conversation_id not in self.conversations:
                return {}

            conversation_info = self.conversations[conversation_id]
            delta = self._create_conversation_delta(event, conversation_info)
            await self._process_event(event, conversation_info, delta)

            return delta.to_dict()

    async def delete_from_conversation(self,
                                       incoming_event: Any = None,
                                       outgoing_event: Any = None) -> Optional[Dict[str, Any]]:
        """Handle deletion of messages from a conversation

        Args:
            incoming_event: Incoming event object
            outgoing_event: Outgoing event object

        Returns:
            Dictionary with delta information or None if conversation info can't be determined
        """
        event = incoming_event or outgoing_event
        deleted_ids = await self._get_deleted_message_ids(event)
        conversation_info = await self._get_conversation_info_to_delete_from(event, deleted_ids)

        if not conversation_info:
            return {}

        delta = self._create_conversation_delta(event, conversation_info)

        async with self._lock:
            for msg_id in deleted_ids:
                cached_msg = await self.message_cache.get_message_by_id(
                    conversation_id=conversation_info.conversation_id,
                    message_id=msg_id
                )
                if cached_msg:
                    if not cached_msg.is_from_bot:
                        delta.deleted_message_ids.append(msg_id)

                    self.thread_handler.remove_thread_info(
                        conversation_info, cached_msg
                    )
                    await self.message_cache.delete_message(
                        conversation_info.conversation_id, msg_id
                    )

                    if hasattr(conversation_info, "messages"):
                        conversation_info.messages.discard(msg_id)
                    if hasattr(conversation_info, "pinned_messages"):
                        conversation_info.pinned_messages.discard(msg_id)

            return delta.to_dict()

    async def _update_attachment(self,
                                 conversation_info: BaseConversationInfo,
                                 attachments: List[Dict[str, Any]] = []) -> List[Dict[str, Any]]:
        """Update attachment info in conversation info

        Args:
            conversation_info: Conversation info object
            attachments: List of attachment dictionaries

        Returns:
            List of dictionaries with attachment information
        """
        result = []

        for attachment in attachments:
            if not attachment:
                continue

            await self.attachment_cache.add_attachment(
                conversation_info.conversation_id, attachment
            )
            conversation_info.attachments.add(attachment["attachment_id"])
            result.append({
                "attachment_id": attachment["attachment_id"],
                "filename": attachment["filename"],
                "content_type": attachment["content_type"],
                "content": attachment["content"],
                "size": attachment["size"],
                "processable": attachment["processable"],
                "url": attachment["url"]
            })

        return result

    async def _get_or_create_conversation_info(self, event: Any) -> Optional[BaseConversationInfo]:
        """Get existing conversation info or create a new one

        Args:
            event: Event object

        Returns:
           Conversation info object or None if conversation can't be determined
        """
        platform_conversation_id = await self._get_platform_conversation_id(event["message"])
        if not platform_conversation_id:
            return None

        conversation_id = self._generate_deterministic_conversation_id(platform_conversation_id)
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        self.conversations[conversation_id] = self._create_conversation_info(
            platform_conversation_id=platform_conversation_id,
            conversation_id=conversation_id,
            conversation_type=await self._get_conversation_type(event["message"]),
            server=event.get("server", None)
        )

        return self.conversations[conversation_id]

    def _generate_deterministic_conversation_id(self, platform_id):
        """Generate a deterministic standardized ID from platform-specific information.

        Args:
            platform_id: The platform's native conversation ID

        Returns:
            A deterministic standardized ID that will be the same each time
            for the same input parameters if the platform_id exists
        """
        if platform_id.startswith(f"{self.adapter_type}_"):
            return platform_id

        hash_obj = hashlib.sha256(str(platform_id).encode("utf-8"))
        hash_bytes = hash_obj.digest()
        b64_id = base64.b64encode(hash_bytes[:15]).decode("ascii").rstrip("=")
        alphanumeric_id = b64_id.replace("+", "A").replace("/", "B")

        return f"{self.adapter_type}_{alphanumeric_id}"

    def _get_custom_conversation_name(self, conversation_info: BaseConversationInfo) -> str:
        """Get the custom conversation name

        Args:
            conversation_info: Conversation info object

        Returns:
            Custom conversation name
        """
        name = "DM"


        for user in conversation_info.known_members.values():
            if not user.is_bot:
                name += f"_{user.display_name.replace(' ', '_')}"

        return name

    def _get_mentions(self, delta: ConversationDelta, cached_msg: CachedMessage, message: Any) -> List[str]:
        """Get the mentions for a given cached message

        Args:
            delta: Conversation delta object
            cached_msg: Cached message object
            message: Raw message object from the adapter

        Returns:
            List of mentions
        """
        if delta.history_fetching_in_progress:
            return []

        return self._get_bot_mentions(cached_msg, message)

    def _create_conversation_delta(self,
                                   event: Dict[str, Any],
                                   conversation_info: BaseConversationInfo) -> ConversationDelta:
        """Create a conversation delta

        Args:
            event: Event object
            conversation_info: Conversation info object

        Returns:
            Conversation delta object
        """
        delta = ConversationDelta(
            conversation_id=conversation_info.conversation_id,
            conversation_name=conversation_info.conversation_name,
            server_name=conversation_info.server_name
        )

        if conversation_info.just_started:
            delta.fetch_history = True
            conversation_info.just_started = False

        try:
            delta.history_fetching_in_progress = event.get("history_fetching_in_progress", False)
        except Exception as e:
            pass

        return delta

    async def _create_message(self,
                              message: Any,
                              conversation_info: BaseConversationInfo,
                              user_info: UserInfo,
                              thread_info: ThreadInfo) -> CachedMessage:
        """Create a new message in the cache

        Args:
            message: Message object
            conversation_info: Conversation info object
            user_info: User info object
            thread_info: Thread info object

        Returns:
            Cached message object
        """
        message_data = self.message_builder.reset() \
            .with_basic_info(message, conversation_info) \
            .with_sender_info(user_info) \
            .with_thread_info(thread_info) \
            .with_content(message) \
            .build()
        cached_msg = await self.message_cache.add_message(message_data)

        return cached_msg

    async def _update_delta_list(self,
                                 conversation_id: str,
                                 delta: ConversationDelta,
                                 list_to_update: str,
                                 message_id: Optional[str] = None,
                                 cached_msg: Optional[CachedMessage] = None,
                                 attachments: Optional[List[Dict[str, Any]]] = [],
                                 mentions: Optional[List[str]] = []) -> None:
        """Add a migrated message to the delta

        Args:
            conversation_id: Conversation ID
            delta: Delta object to update
            list_to_update: List to update
            message_id: Message ID
            cached_msg: Cached message object
            attachments: List of attachment dictionaries
            mentions: List of mentions
        """
        if not delta.history_fetching_in_progress and cached_msg and cached_msg.is_from_bot:
            return

        if not cached_msg:
            cached_msg = await self.message_cache.get_message_by_id(conversation_id, message_id)

        if cached_msg and (cached_msg.text or attachments):
            getattr(delta, list_to_update).append({
                "message_id": cached_msg.message_id,
                "conversation_id": conversation_id,
                "sender":  {
                    "user_id": cached_msg.sender_id,
                    "display_name": cached_msg.sender_name
                },
                "text": cached_msg.text,
                "timestamp": cached_msg.timestamp,
                "edit_timestamp": cached_msg.edit_timestamp,
                "edited": cached_msg.edited,
                "thread_id": cached_msg.thread_id,
                "is_direct_message": cached_msg.is_direct_message,
                "attachments": attachments,
                "mentions": mentions
            })

    def _update_server_metadata(self,
                                conversation: BaseConversationInfo,
                                server_id: str,
                                new_name: str) -> bool:
        """Update the server metadata

        Args:
            conversation: ConversationInfo object
            server_id: Server ID
            new_name: New server name

        Returns:
            True if the server metadata was updated, False otherwise
        """
        if conversation.server_id != server_id:
            return False
        conversation.server_name = new_name
        return True

    def _update_conversation_metadata(self,
                                      conversation: BaseConversationInfo,
                                      platform_conversation_id: str,
                                      new_name: str) -> bool:
        """Update the conversation metadata

        Args:
            conversation: ConversationInfo object
            platform_conversation_id: Platform conversation ID
            new_name: New conversation name

        Returns:
            True if the conversation metadata was updated, False otherwise
        """
        if conversation.platform_conversation_id != platform_conversation_id or \
           conversation.conversation_name == new_name:
            return False
        conversation.conversation_name = new_name
        return True

    @abstractmethod
    async def update_metadata(self, event: Any) -> Dict[str, Any]:
        """Update the conversation metadata"""
        raise NotImplementedError("Child classes must implement _update_metadata")

    @abstractmethod
    async def _get_platform_conversation_id(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a message"""
        raise NotImplementedError("Child classes must implement get_conversation_id")

    @abstractmethod
    async def _get_conversation_id_from_update(self, message: Any) -> Optional[str]:
        """Get the conversation ID from a message"""
        raise NotImplementedError("Child classes must implement _get_conversation_id_from_update_message")

    @abstractmethod
    async def _get_conversation_type(self, message: Any) -> Optional[str]:
        """Get the conversation type from a message"""
        raise NotImplementedError("Child classes must implement get_conversation_type")

    @abstractmethod
    async def _update_conversation_name(self, event: Any, conversation_info: Any) -> None:
        """Update the conversation name"""
        raise NotImplementedError("Child classes must implement _update_conversation_name")

    @abstractmethod
    def _create_conversation_info(self,
                                  platform_conversation_id: str,
                                  conversation_id: str,
                                  conversation_type: str,
                                  server: Optional[Any] = None) -> BaseConversationInfo:
        """Create a conversation info object"""
        raise NotImplementedError("Child classes must implement create_conversation_info")

    @abstractmethod
    async def _get_user_info(self, event: Dict[str, Any], conversation_info: BaseConversationInfo) -> UserInfo:
        """Get the user info for a given event and conversation info"""
        raise NotImplementedError("Child classes must implement _get_user_info")

    @abstractmethod
    def _get_bot_mentions(self, cached_msg: CachedMessage, message: Any) -> List[str]:
        """Get the bot mentions for a given conversation info and cached message"""
        raise NotImplementedError("Child classes must implement _get_bot_mentions")

    @abstractmethod
    async def _get_deleted_message_ids(self, event: Any) -> List[str]:
        """Get the deleted message IDs from an event"""
        raise NotImplementedError("Child classes must implement _get_deleted_message_ids")

    @abstractmethod
    async def _get_conversation_info_to_delete_from(self,
                                                    event: Any,
                                                    deleted_ids: List[str] = []) -> Optional[BaseConversationInfo]:
        """Get the conversation info to delete from"""
        raise NotImplementedError("Child classes must implement _get_conversation_info_to_delete_from")

    @abstractmethod
    async def _process_event(self,
                             event: Dict[str, Any],
                             conversation_info: BaseConversationInfo,
                             delta: ConversationDelta) -> None:
        """Process an event based on event type"""
        raise NotImplementedError("Child classes must implement _process_event")
