from src.core.cache.message_cache import CachedMessage
from src.core.conversation.base_data_classes import ConversationDelta
from src.core.conversation.base_reaction_handler import BaseReactionHandler
from src.core.utils.emoji_converter import EmojiConverter

class ReactionHandler:
    """Handles message reactions"""

    @staticmethod
    def update_message_reactions(op: str,
                                 cached_msg: CachedMessage,
                                 reaction: str,
                                 delta: ConversationDelta) -> None:
        """Update delta with reaction changes

        Args:
            op: Operation to perform
            cached_msg: Cached message object
            reaction: Reaction to update
            delta: Current delta object
        """
        reaction = EmojiConverter.get_instance().platform_specific_to_standard(reaction)

        if op == "reaction_added":
            BaseReactionHandler.add_reaction(cached_msg, reaction)
            delta.added_reactions = [reaction]
        elif op == "reaction_removed":
            BaseReactionHandler.remove_reaction(cached_msg, reaction)
            delta.removed_reactions = [reaction]
