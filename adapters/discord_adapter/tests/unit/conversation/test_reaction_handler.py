import pytest

from adapters.discord_adapter.adapter.conversation.reaction_handler import ReactionHandler
from core.cache.message_cache import CachedMessage
from core.conversation.base_data_classes import ConversationDelta

class TestReactionHandler:
    """Tests for the Discord ReactionHandler class"""

    @pytest.fixture
    def cached_message(self):
        """Create a cached message with initial reactions"""
        cached_msg = CachedMessage(
            message_id="123",
            conversation_id="456",
            text="Test message",
            sender_id="789",
            sender_name="Test User",
            timestamp=1234567890000,
            is_from_bot=False,
            thread_id=None,
            reactions={"thumbs_up": 1}  # Initial reaction
        )
        return cached_msg

    @pytest.fixture
    def delta(self):
        """Create a ConversationDelta object"""
        return ConversationDelta(conversation_id="456", message_id="123")

    def test_update_message_reactions_add(self, cached_message, delta):
        """Test updating delta when a reaction is added"""
        ReactionHandler.update_message_reactions(
            "added_reaction", cached_message, "❤️", delta
        )

        assert len(delta.added_reactions) == 1
        assert delta.added_reactions[0] == "red_heart"
        assert not delta.removed_reactions

        assert "red_heart" in cached_message.reactions
        assert cached_message.reactions["red_heart"] == 1

    def test_update_message_reactions_remove(self, cached_message, delta):
        """Test updating delta when a reaction is removed"""
        ReactionHandler.update_message_reactions(
            "removed_reaction", cached_message, "👍", delta
        )

        assert len(delta.removed_reactions) == 1
        assert delta.removed_reactions[0] == "thumbs_up"
        assert not delta.added_reactions
        assert "thumbs_up" not in cached_message.reactions  # Should be removed
