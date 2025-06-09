from src.core.cache.message_cache import CachedMessage

class BaseReactionHandler:
    """Handles message reactions"""

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
