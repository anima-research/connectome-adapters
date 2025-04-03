import asyncio
import os

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.conversation.base_data_classes import BaseConversationInfo, ConversationDelta

from core.cache.message_cache import MessageCache, CachedMessage
from core.cache.attachment_cache import AttachmentCache, CachedAttachment
from core.conversation.base_data_classes import BaseConversationInfo, UserInfo, ThreadInfo
from core.utils.config import Config

class BaseManager(ABC):
    """Tracks and manages information about a conversations"""

    def __init__(self, config: Config, start_maintenance=False):
        """Initialize the conversation manager

        Args:
            config: Config instance
            start_maintenance: Whether to start the maintenance loop
        """
        self.config = config
        self.conversations: Dict[str, BaseConversationInfo] = {}
        self._lock = asyncio.Lock()
        self.message_cache = MessageCache(config, start_maintenance)
        self.attachment_cache = AttachmentCache(config, start_maintenance)
        self.message_builder = None # set by child class
        self.thread_handler = None # set by child class

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
            msg_dict = msg.cache_to_dict().copy()
            msg_dict["attachments"] = []

            for attachment_id in msg.attachments:
                attachment = self._attachment_to_dict(
                    self.attachment_cache.get_attachment(attachment_id)
                )
                if attachment:
                    msg_dict["attachments"].append(attachment)

            result.append(msg_dict)

        return result

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

            conversation_info = await self._get_or_create_conversation_info(message)
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

            delta = self._create_conversation_delta(event, conversation_info)
            delta.message_id = cached_msg.message_id

            await self._update_delta_list(
                conversation_id=conversation_info.conversation_id,
                delta=delta,
                list_to_update="added_messages",
                cached_msg=cached_msg,
                attachments=attachments
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

            cached_attachment = await self.attachment_cache.add_attachment(
                conversation_info.conversation_id, attachment
            )
            result.append(self._attachment_to_dict(cached_attachment))
            conversation_info.attachments.add(cached_attachment.attachment_id)

        return result

    async def _get_or_create_conversation_info(self, message: Any) -> Optional[BaseConversationInfo]:
        """Get existing conversation info or create a new one

        Args:
            message: Message object

        Returns:
           Conversation info object or None if conversation can't be determined
        """
        conversation_id = await self._get_conversation_id(message)

        if not conversation_id:
            return None
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        self.conversations[conversation_id] = self._create_conversation_info(
            conversation_id,
            await self._get_conversation_type(message),
            await self._get_conversation_name(message)
        )

        return self.conversations[conversation_id]

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
        delta = ConversationDelta(conversation_id=conversation_info.conversation_id)

        if conversation_info.just_started:
            delta.fetch_history = True
            conversation_info.just_started = False

        try:
            delta.display_bot_messages = event.get("display_bot_messages", False)
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
            .with_basic_info(message, conversation_info.conversation_id) \
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
                                 attachments: Optional[List[Dict[str, Any]]] = [],
                                 message_id: Optional[str] = None,
                                 cached_msg: Optional[CachedMessage] = None) -> None:
        """Add a migrated message to the delta

        Args:
            conversation_id: Conversation ID
            delta: Delta object to update
            list_to_update: List to update
            attachments: List of attachment dictionaries
            message_id: Message ID
            cached_msg: Cached message object
        """
        if not delta.display_bot_messages and cached_msg and cached_msg.is_from_bot:
            return

        if not cached_msg:
            cached_msg = await self.message_cache.get_message_by_id(conversation_id, message_id)

        if cached_msg:
            getattr(delta, list_to_update).append({
                "message_id": cached_msg.message_id,
                "conversation_id": conversation_id,
                "sender":  {
                    "user_id": cached_msg.sender_id,
                    "display_name": cached_msg.sender_name
                },
                "text": cached_msg.text,
                "timestamp": cached_msg.timestamp,
                "thread_id": cached_msg.thread_id,
                "attachments": attachments
            })

    def _attachment_to_dict(self, attachment: CachedAttachment) -> Optional[Dict[str, Any]]:
        """Convert attachment to dict

        Args:
            message: Attachment cache object

        Returns:
            Attachment dict or {} if attachment is None
        """
        if not attachment:
            return {}

        return {
            "attachment_id": attachment.attachment_id,
            "attachment_type": attachment.attachment_type,
            "file_extension": attachment.file_extension,
            "file_path": os.path.join(
                self.config.get_setting("attachments", "storage_dir"),
                attachment.file_path
            ),
            "size": attachment.size
        }

    @abstractmethod
    async def _get_conversation_id(self, message: Any) -> Optional[str]:
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
    async def _get_conversation_name(self, message: Any) -> Optional[str]:
        """Get the conversation name from a message"""
        raise NotImplementedError("Child classes must implement get_conversation_name")

    @abstractmethod
    def _create_conversation_info(self,
                                  conversation_id: str,
                                  conversation_type: str,
                                  conversation_name: Optional[str] = None) -> BaseConversationInfo:
        """Create a conversation info object"""
        raise NotImplementedError("Child classes must implement create_conversation_info")

    @abstractmethod
    async def _get_user_info(self, event: Dict[str, Any], conversation_info: BaseConversationInfo) -> UserInfo:
        """Get the user info for a given event and conversation info"""
        raise NotImplementedError("Child classes must implement _get_user_info")

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
