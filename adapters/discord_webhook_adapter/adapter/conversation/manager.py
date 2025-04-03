from typing import Any, Dict, Optional
from adapters.discord_webhook_adapter.adapter.conversation.data_classes import ConversationInfo
from core.utils.config import Config

class Manager():
    """Tracks and manages information about Discord webhook conversations"""

    def __init__(self, config: Config):
        """Initialize the conversation manager

        Args:
            config: Config instance
        """
        self.config = config
        self.conversations: Dict[str, ConversationInfo] = {}

    def get_conversation(self, conversation_id: str) -> Optional[ConversationInfo]:
        """Get a conversation by ID

        Args:
            conversation_id: ID of the conversation to get

        Returns:
            ConversationInfo object or None if conversation not found
        """
        return self.conversations.get(conversation_id, None)

    def add_to_conversation(self, event: Dict[str, Any]) -> None:
        """Create a new conversation or add a message to an existing conversation

        Args:
            event: Event object that contains discord response and webhook info
                   (we presume that certain fields are present in the event,
                   yet do not know for sure)
        """
        if not event:
            return

        conversation_info = self._get_or_create_conversation_info(event)
        if not conversation_info:
            return

        message_id = str(event.get("id", ""))
        if message_id:
            conversation_info.messages.add(message_id)
            conversation_info.message_count += 1

    def delete_from_conversation(self, event: Dict[str, Any]) -> None:
        """Handle deletion of messages from a conversation

        Args:
            event: Event object sent from LLM
                   (i.e. conversation_id and message_id presence is validated)
        """
        if not event:
            return

        conversation_info = self.conversations.get(event["conversation_id"], None)
        if not conversation_info:
            return

        if event["message_id"] in conversation_info.messages:
            conversation_info.messages.discard(event["message_id"])
            conversation_info.message_count -= 1
            if conversation_info.message_count == 0:
                del self.conversations[conversation_info.conversation_id]

    def _get_or_create_conversation_info(self, event: Dict[str, Any]) -> Optional[ConversationInfo]:
        """Get or create a conversation info object for a given event

        Args:
            event: Event object that should contain the following keys:

        Returns:
            ConversationInfo object or None if conversation info can't be determined
        """
        conversation_id = event.get("conversation_id", None)

        if not conversation_id:
            return None

        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ConversationInfo(
                conversation_id=conversation_id,
                webhook_url=event.get("webhook_url", None),
                webhook_name=event.get("webhook_name", None)
            )

        return self.conversations[conversation_id]
