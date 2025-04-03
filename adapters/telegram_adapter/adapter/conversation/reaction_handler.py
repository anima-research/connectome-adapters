import emoji
from typing import Dict, Any, List

from core.cache.message_cache import CachedMessage
from core.conversation.base_data_classes import ConversationDelta

class ReactionHandler:
    """Handles message reactions"""

    @staticmethod
    async def extract_reactions(reactions: Any) -> Dict[str, int]:
        """Extract reaction data from a Telethon MessageReactions object

        Args:
            reactions: Telethon MessageReactions object

        Returns:
            Dictionary mapping emoji to count
        """
        reaction_data = {}

        if not reactions or not hasattr(reactions, "results"):
            return reaction_data

        for result in reactions.results:
            if hasattr(result, "reaction") and hasattr(result.reaction, "emoticon"):
                emoji_name = emoji.demojize(result.reaction.emoticon).strip(":")
                count = getattr(result, "count", 1)
                reaction_data[emoji_name] = count

        return reaction_data

    @staticmethod
    def get_added_reactions(old_reactions: Dict[str, int],
                            new_reactions: Dict[str, int]) -> List[str]:
        """Get reactions that were added

        Args:
            old_reactions: Previous reactions
            new_reactions: Current reactions

        Returns:
            List of added emoji reactions
        """
        reactions = []

        for emoji, count in new_reactions.items():
            old_count = old_reactions.get(emoji, 0)
            if count > old_count:
                reactions.append(emoji)

        return reactions

    @staticmethod
    def get_removed_reactions(old_reactions: Dict[str, int],
                              new_reactions: Dict[str, int]) -> List[str]:
        """Get reactions that were removed

        Args:
            old_reactions: Previous reactions
            new_reactions: Current reactions

        Returns:
            List of removed emoji reactions
        """
        reactions = []

        for emoji, count in old_reactions.items():
            new_count = new_reactions.get(emoji, 0)
            if count > new_count:
                reactions.append(emoji)

        return reactions

    @staticmethod
    def update_message_reactions(cached_msg: CachedMessage,
                                 new_reactions: Dict[str, int],
                                 delta: ConversationDelta):
        """Update delta with reaction changes

        Args:
            cached_msg: Cached message object
            new_reactions: New reactions dictionary
            delta: Current delta object
        """
        delta.added_reactions = ReactionHandler.get_added_reactions(
            cached_msg.reactions, new_reactions
        )
        delta.removed_reactions = ReactionHandler.get_removed_reactions(
            cached_msg.reactions, new_reactions
        )
        cached_msg.reactions = new_reactions
