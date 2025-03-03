import asyncio
import logging

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Union, Set, Any

from config import Config
from message_cache import MessageCache, CachedMessage

@dataclass
class ThreadInfo:
    """Information about a thread within a conversation"""
    thread_id: str  # Could be message_thread_id, reply message_id, etc.
    title: Optional[str] = None  # For named threads/topics
    root_message_id: Optional[str] = None  # ID of the message that started the thread
    message_count: int = 0
    last_activity: datetime = None

    def __post_init__(self):
        if self.last_activity is None:
            self.last_activity = datetime.now()

@dataclass
class ConversationInfo:
    """Comprehensive information about a Telegram chat"""
    # Core identifiers
    conversation_id: Union[int, str]
    conversation_type: str  # 'private', 'group', 'supergroup', 'channel'

    # Basic info
    title: Optional[str] = None  # For groups, supergroups, channels
    username: Optional[str] = None  # For users or channels with username
    first_name: Optional[str] = None  # For private chats
    last_name: Optional[str] = None  # For private chats

    # Group/Supergroup specific properties
    is_forum: bool = False  # Whether the group has topics enabled
    all_members_are_administrators: bool = False  # Admin status
    has_protected_content: bool = False  # Content protection

    # Channel specific
    is_public: bool = False  # Has public username

    # Activity tracking
    created_at: datetime = None  # When we first saw this chat
    last_activity: datetime = None  # Last message time
    message_count: int = 0  # Count of messages seen

    # Bot's status in the chat
    bot_is_member: bool = False  # If the bot is a member
    bot_is_admin: bool = False  # If the bot is an admin
    bot_permissions: Dict[str, bool] = field(default_factory=dict)  # What the bot can do

    # Metadata storage
    known_member_ids: Set[int] = field(default_factory=set)  # Users we've seen in this chat
    api_kwargs: Dict[str, Any] = field(default_factory=dict)  # Raw API data

    # Migration tracking
    migrated_from_conversation_id: Optional[Union[int, str]] = None
    migrated_to_conversation_id: Optional[Union[int, str]] = None

    # Add thread tracking
    threads: Dict[str, ThreadInfo] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_activity is None:
            self.last_activity = datetime.now()

class ConversationTracker:
    """Tracks and manages information about Telegram conversations"""

    def __init__(self, message_cache: MessageCache):
        self.conversations: Dict[Union[int, str], ConversationInfo] = {}
        self.migrations: Dict[Union[int, str], Union[int, str]] = {}
        self._lock = asyncio.Lock()
        self.message_cache = message_cache

    async def update_conversation_from_message(self, update) -> Optional[ConversationInfo]:
        """Update conversation information based on a Telegram update"""
        # Extract message from update
        message = self._extract_message_from_update(update)
        if not message or not hasattr(message, 'chat'):
            return None

        # Handle special case for bot messages
        is_bot_message = getattr(update, 'from_bot', False)

        async with self._lock:
            conversation_id = str(message.chat.id)
            conversation_info = await self._get_or_create_conversation(message.chat)

            await self._handle_migrations(message, conversation_info)
            await self._update_conversation_properties(message, conversation_info)

            thread_id = await self._detect_thread_id(message)
            if thread_id:
                root_message_id = await self._determine_root_message_id(message, thread_id)
                await self._update_thread_info(conversation_info, thread_id, root_message_id)

            await self._track_message_sender(message, conversation_info)
            await self._handle_special_events(message, conversation_info)

            if self.message_cache:
                cached_msg = self._create_cached_message(message, thread_id)
                if cached_msg:
                    await self.message_cache.add_message(cached_msg)

            conversation_info.last_activity = datetime.now()
            conversation_info.message_count += 1

            return conversation_info

    def _extract_message_from_update(self, update) -> Optional[Any]:
        """Extract the message object from different update types"""
        if hasattr(update, 'message') and update.message:
            return update.message
        elif hasattr(update, 'edited_message') and update.edited_message:
            return update.edited_message
        elif hasattr(update, 'channel_post') and update.channel_post:
            return update.channel_post
        elif hasattr(update, 'edited_channel_post') and update.edited_channel_post:
            return update.edited_channel_post
        return None

    async def _get_or_create_conversation(self, conversation) -> ConversationInfo:
        """Get existing conversation or create a new one"""
        conversation_id = str(conversation.id)

        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        conversation_info = ConversationInfo(
            conversation_id=conversation_id,
            conversation_type=conversation.type.value,  # Convert enum to string
        )

        if hasattr(conversation, 'title'):
            conversation_info.title = conversation.title
        if hasattr(conversation, 'username'):
            conversation_info.username = conversation.username
        if hasattr(conversation, 'first_name'):
            conversation_info.first_name = conversation.first_name
        if hasattr(conversation, 'last_name'):
            conversation_info.last_name = conversation.last_name

        self.conversations[conversation_id] = conversation_info
        logging.info(f"New conversation tracked: {conversation_id} ({conversation_info.conversation_type})")

        return conversation_info

    async def _handle_migrations(self, message, conversation_info):
        """Handle group/supergroup migrations"""
        conversation_id = str(message.chat.id)

        if hasattr(message, 'migrate_to_chat_id') and message.migrate_to_chat_id:
            new_conversation_id = str(message.migrate_to_chat_id)
            self.migrations[conversation_id] = new_conversation_id
            conversation_info.migrated_to_conversation_id = new_conversation_id
            logging.info(f"Conversation {conversation_id} migrated to {new_conversation_id}")

        if hasattr(message, 'migrate_from_chat_id') and message.migrate_from_chat_id:
            old_conversation_id = str(message.migrate_from_chat_id)
            self.migrations[old_conversation_id] = conversation_id
            conversation_info.migrated_from_conversation_id = old_conversation_id
            logging.info(f"This conversation {conversation_id} was migrated from {old_conversation_id}")

            if old_conversation_id in self.conversations:
                old_info = self.conversations[old_conversation_id]
                old_info.migrated_to_conversation_id = conversation_id

                if not conversation_info.title and old_info.title:
                    conversation_info.title = old_info.title

                conversation_info.known_member_ids.update(old_info.known_member_ids)

    async def _update_conversation_properties(self, message, conversation_info):
        """Update various conversation properties from message"""
        chat = message.chat

        if hasattr(chat, 'title'):
            conversation_info.title = chat.title
        if hasattr(chat, 'username'):
            conversation_info.username = chat.username
        if hasattr(chat, 'first_name'):
            conversation_info.first_name = chat.first_name
        if hasattr(chat, 'last_name'):
            conversation_info.last_name = chat.last_name
        if hasattr(chat, 'is_forum'):
            conversation_info.is_forum = chat.is_forum

        if hasattr(chat, 'api_kwargs'):
            conversation_info.api_kwargs.update(chat.api_kwargs)

            if 'all_members_are_administrators' in chat.api_kwargs:
                conversation_info.all_members_are_administrators = chat.api_kwargs['all_members_are_administrators']
            if 'has_protected_content' in chat.api_kwargs:
                conversation_info.has_protected_content = chat.api_kwargs['has_protected_content']

    async def _detect_thread_id(self, message) -> Optional[str]:
        """Detect thread ID from message"""
        if hasattr(message, 'message_thread_id') and message.message_thread_id:
            return str(message.message_thread_id)
        elif hasattr(message, 'reply_to_message') and message.reply_to_message:
            return f"reply_{message.reply_to_message.message_id}"

        return None

    async def _determine_root_message_id(self, message, thread_id) -> Optional[str]:
        """Determine the root message ID for a thread"""
        if thread_id and not thread_id.startswith("reply_"):
            # This is a forum thread - use thread ID as root
            if hasattr(message, 'message_id') and message.message_id == int(thread_id):
                return str(message.message_id)
            else:
                return thread_id

        # For reply chains, use the replied-to message as root
        elif hasattr(message, 'reply_to_message') and message.reply_to_message:
            return str(message.reply_to_message.message_id)

        return None

    async def _update_thread_info(self, conversation_info, thread_id, root_message_id):
        """Update thread information in conversation"""
        if not thread_id:
            return

        if thread_id not in conversation_info.threads:
            conversation_info.threads[thread_id] = ThreadInfo(
                thread_id=thread_id,
                root_message_id=root_message_id
            )

        thread = conversation_info.threads[thread_id]
        thread.message_count += 1
        thread.last_activity = datetime.now()

        if not thread.root_message_id and root_message_id:
            thread.root_message_id = root_message_id

    async def _track_message_sender(self, message, conversation_info):
        """Track information about message sender"""
        if hasattr(message, 'from_user') and message.from_user:
            user_id = message.from_user.id
            conversation_info.known_member_ids.add(user_id)

            if hasattr(message, 'bot') and message.from_user.id == message.bot.id:
                conversation_info.bot_is_member = True

        if hasattr(message, 'sender_chat') and message.sender_chat:
            sender_chat_id = message.sender_chat.id
            if sender_chat_id == conversation_info.conversation_id:
                if hasattr(message.sender_chat, 'username') and message.sender_chat.username:
                    conversation_info.is_public = True
                    conversation_info.username = message.sender_chat.username

    async def _handle_special_events(self, message, conversation_info):
        """Handle special events like member changes, group creation, etc."""
        if hasattr(message, 'new_chat_members') and message.new_chat_members:
            for user in message.new_chat_members:
                conversation_info.known_member_ids.add(user.id)
                if hasattr(message, 'bot') and user.id == message.bot.id:
                    conversation_info.bot_is_member = True

        if hasattr(message, 'left_chat_member') and message.left_chat_member:
            if hasattr(message, 'bot') and message.left_chat_member.id == message.bot.id:
                conversation_info.bot_is_member = False

        is_new_conversation = False
        if hasattr(message, 'group_chat_created') and message.group_chat_created:
            logging.info(f"Group chat created: {conversation_info.conversation_id}")
            is_new_conversation = True

        if hasattr(message, 'supergroup_chat_created') and message.supergroup_chat_created:
            logging.info(f"Supergroup chat created: {conversation_info.conversation_id}")
            is_new_conversation = True

        if hasattr(message, 'channel_chat_created') and message.channel_chat_created:
            logging.info(f"Channel created: {conversation_info.conversation_id}")
            is_new_conversation = True

        return is_new_conversation

    def _create_cached_message(self, message, thread_id=None) -> Optional[CachedMessage]:
        """Create a CachedMessage from a Telegram message"""
        try:
            reply_to_message_id = None
            if hasattr(message, 'reply_to_message') and message.reply_to_message:
                reply_to_message_id = str(message.reply_to_message.message_id)

            text = None
            if hasattr(message, 'text'):
                text = message.text
            elif hasattr(message, 'caption'):
                text = message.caption

            return CachedMessage(
                message_id=str(message.message_id),
                conversation_id=str(message.chat.id),
                thread_id=thread_id,
                sender_id=str(message.from_user.id if message.from_user else 0),
                sender_name=(message.from_user.first_name if message.from_user else "Unknown"),
                text=text,
                timestamp=message.date,
                is_from_bot=bool(message.from_user and message.from_user.is_bot),
                reply_to_message_id=reply_to_message_id,
                media_info=None
            )
        except Exception as e:
            logging.error(f"Error creating cached message: {e}")
            return None

    async def record_bot_message(self, message, reply_to_message_id=None):
        """Record a message sent by our bot"""
        thread_id = None
        if reply_to_message_id:
            thread_id = f"reply_{reply_to_message_id}"

        conversation_id = str(message.chat.id)
        conversation_info = await self._get_or_create_conversation(message.chat)

        if thread_id:
            await self._update_thread_info(conversation_info, thread_id, str(reply_to_message_id))

        logging.error(f"Bot message {message}")

        cached_msg = CachedMessage(
            message_id=str(message.message_id),
            conversation_id=conversation_id,
            thread_id=thread_id,
            sender_id=str(message.from_user.id),
            sender_name=message.from_user.username or "Bot",
            text=message.text,
            timestamp=message.date,
            is_from_bot=True,
            reply_to_message_id=str(reply_to_message_id) if reply_to_message_id else None
        )
        await self.message_cache.add_message(cached_msg)

        return conversation_info

    def get_conversation_info(self, conversation_id: Union[int, str]) -> Optional[ConversationInfo]:
        """Get information about a specific chat"""
        # Check for migration
        if conversation_id in self.migrations:
            new_id = self.migrations[conversation_id]
            logging.debug(f"Conversation ID {conversation_id} was migrated to {new_id}")
            conversation_id = new_id

        return self.conversations.get(conversation_id)

    def get_all_conversations(self, conversation_type: Optional[str] = None) -> List[ConversationInfo]:
        """Get all tracked conversations, optionally filtered by type"""
        if conversation_type:
            return [conversation for conversation in self.conversations.values() if conversation.conversation_type == conversation_type]
        return list(self.conversations.values())

    def get_active_conversations(self, minutes: int = 60) -> List[ConversationInfo]:
        """Get conversations with activity in the last X minutes"""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [conversation for conversation in self.conversations.values() if conversation.last_activity >= cutoff]

    def get_conversation_display_name(self, conversation_id: Union[int, str]) -> str:
        """Get a human-readable name for the conversation"""
        conversation_info = self.get_conversation_info(conversation_id)
        if not conversation_info:
            return f"Unknown Chat ({conversation_id})"

        if conversation_info.conversation_type == 'private':
            parts = [part for part in [conversation_info.first_name, conversation_info.last_name] if part]
            return " ".join(parts) or f"User {conversation_id}"
        else:
            return conversation_info.title or f"{conversation_info.conversation_type.capitalize()} {conversation_id}"

    def get_user_conversations(self, user_id: int) -> List[ConversationInfo]:
        """Get all conversations where we've seen a specific user"""
        return [
            conversation for conversation in self.conversations.values()
            if user_id in conversation.known_member_ids
        ]

    def get_bot_member_conversations(self) -> List[ConversationInfo]:
        """Get all conversations where our bot is a member"""
        return [conversation for conversation in self.conversations.values() if conversation.bot_is_member]

    def get_conversation_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked conversations"""
        conversation_types = {}
        total_messages = 0
        active_count = len(self.get_active_conversations())

        for conversation in self.conversations.values():
            conversation_types[conversation.conversation_type] = conversation_types.get(conversation.conversation_type, 0) + 1
            total_messages += conversation.message_count

        return {
            "total_conversations": len(self.conversations),
            "active_conversations": active_count,
            "by_type": conversation_types,
            "total_messages": total_messages
        }

    def get_threads_in_conversation(self, conversation_id: Union[int, str]) -> List[ThreadInfo]:
        """Get all threads in a conversation"""
        conv_info = self.get_conversation_info(conversation_id)
        if not conv_info:
            return []

        return list(conv_info.threads.values())

    def get_thread_info(self, conversation_id: Union[int, str], thread_id: str) -> Optional[ThreadInfo]:
        """Get information about a specific thread"""
        conv_info = self.get_conversation_info(conversation_id)
        if not conv_info:
            return None

        return conv_info.threads.get(thread_id)
