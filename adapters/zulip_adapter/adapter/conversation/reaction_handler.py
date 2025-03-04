import emoji

from typing import Dict, Any

from core.cache.message_cache import CachedMessage
from core.conversation.base_data_classes import ConversationDelta

class ReactionHandler:
    """Handles message reactions"""

    @staticmethod
    def convert_emoji_code_to_symbol(message: Dict[str, Any]) -> str:
        """Convert Zulip emoji data to an actual emoji symbol using the emoji package

        Args:
            message: Zulip message object

        Returns:
            Unicode emoji symbol as a string
        """
        emoji_name = message.get("emoji_name", "")
        reaction_type = message.get("reaction_type", "")

        if reaction_type != "unicode_emoji":
            return str(emoji_name)

        emoji_symbol = emoji.emojize(f":{emoji_name}:", language='alias')

        if emoji_symbol == f":{emoji_name}:":
            emoji_code = message.get("emoji_code", "")
            if emoji_code:
                try:
                    code_point = int(emoji_code, 16)
                    return str(chr(code_point))
                except (ValueError, TypeError):
                    pass

        return emoji_symbol

    @staticmethod
    def add_reaction(cached_msg: CachedMessage, reaction: str) -> None:
        """Add a reaction to the message

        Args:
            cached_msg: Cached message object
            reaction: Reaction to add
        """
        if reaction in cached_msg.reactions:
            cached_msg.reactions[reaction] += 1
        else:
            cached_msg.reactions[reaction] = 1

    @staticmethod
    def remove_reaction(cached_msg: CachedMessage, reaction: str) -> None:
        """Remove a reaction from the message

        Args:
            cached_msg: Cached message object
            reaction: Reaction to remove
        """
        if reaction in cached_msg.reactions:
            cached_msg.reactions[reaction] -= 1
            if cached_msg.reactions[reaction] == 0:
                del cached_msg.reactions[reaction]

    @staticmethod
    def update_message_reactions(message: Dict[str, Any],
                                 cached_msg: CachedMessage,
                                 delta: ConversationDelta) -> ConversationDelta:
        """Update delta with reaction changes

        Args:
            message: Zulip message object
            cached_msg: Cached message object
            delta: Current delta object

        Returns:
            Updated delta object
        """
        reaction = message.get("emoji", None) or ReactionHandler.convert_emoji_code_to_symbol(message)

        if message.get("op", None) == "add":
            ReactionHandler.add_reaction(cached_msg, reaction)
            delta.added_reactions = [] if cached_msg.is_from_bot else [reaction]
        elif message.get("op", None) == "remove":
            ReactionHandler.remove_reaction(cached_msg, reaction)
            delta.removed_reactions = [] if cached_msg.is_from_bot else [reaction]

        return delta
