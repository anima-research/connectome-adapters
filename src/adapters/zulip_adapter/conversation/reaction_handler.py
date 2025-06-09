import csv
import os
from typing import Dict, Any

from src.core.cache.message_cache import CachedMessage
from src.core.conversation.base_data_classes import ConversationDelta
from src.core.conversation.base_reaction_handler import BaseReactionHandler
from src.core.utils.emoji_converter import EmojiConverter

class ReactionHandler:
    """Handles message reactions"""

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
        reaction = EmojiConverter.get_instance().platform_specific_to_standard(
            str(message.get("emoji_name", ""))
        )

        if message.get("op", None) == "add" and reaction:
            BaseReactionHandler.add_reaction(cached_msg, reaction)
            delta.added_reactions = [reaction]
        elif message.get("op", None) == "remove" and reaction:
            BaseReactionHandler.remove_reaction(cached_msg, reaction)
            delta.removed_reactions = [reaction]
