import emoji

from core.cache.message_cache import CachedMessage
from core.conversation.base_data_classes import ConversationDelta
from core.conversation.base_reaction_handler import BaseReactionHandler

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
        reaction = emoji.demojize(reaction).strip(":")

        if op == "added_reaction":
            BaseReactionHandler.add_reaction(cached_msg, reaction)
            delta.added_reactions = [reaction]
        elif op == "removed_reaction":
            BaseReactionHandler.remove_reaction(cached_msg, reaction)
            delta.removed_reactions = [reaction]
