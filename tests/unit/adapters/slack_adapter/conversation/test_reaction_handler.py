import pytest
from unittest.mock import MagicMock, patch
from src.core.cache.message_cache import CachedMessage
from src.core.conversation.base_data_classes import ConversationDelta
from src.adapters.slack_adapter.conversation.reaction_handler import ReactionHandler
from src.core.utils.emoji_converter import EmojiConverter

class TestReactionHandler:
    """Tests for the Slack ReactionHandler class"""

    @pytest.fixture
    def cached_message(self):
        """Create a cached message with initial reactions"""
        cached_msg = CachedMessage(
            message_id="123",
            conversation_id="T12345/C67890",
            text="Test message",
            sender_id="U12345",
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
        return ConversationDelta(conversation_id="T12345/C67890", message_id="123")

    def test_update_message_reactions_add(self, cached_message, delta):
        """Test updating delta when a reaction is added"""
        instance_mock = MagicMock()
        instance_mock.platform_specific_to_standard.return_value = "red_heart"

        with patch.object(EmojiConverter, "_instance", instance_mock):
            ReactionHandler.update_message_reactions(
                "reaction_added",
                cached_message,
                "heart",
                delta
            )

            assert len(delta.added_reactions) == 1
            assert delta.added_reactions[0] == "red_heart"
            assert "red_heart" in cached_message.reactions
            assert cached_message.reactions["red_heart"] == 1
            assert "thumbs_up" in cached_message.reactions  # Original reaction preserved

    def test_update_message_reactions_remove(self, cached_message, delta):
        """Test updating delta when a reaction is removed"""
        instance_mock = MagicMock()
        instance_mock.platform_specific_to_standard.return_value = "thumbs_up"

        with patch.object(EmojiConverter, "_instance", instance_mock):
            ReactionHandler.update_message_reactions(
                "reaction_removed",
                cached_message,
                "+1",
                delta
            )

            assert len(delta.removed_reactions) == 1
            assert delta.removed_reactions[0] == "thumbs_up"
            assert "thumbs_up" not in cached_message.reactions  # Should be removed

    def test_update_message_reactions_add_existing(self, cached_message, delta):
        """Test adding a reaction that already exists"""
        instance_mock = MagicMock()
        instance_mock.platform_specific_to_standard.return_value = "thumbs_up"

        with patch.object(EmojiConverter, "_instance", instance_mock):
            ReactionHandler.update_message_reactions(
                "reaction_added",
                cached_message,
                "+1",
                delta
            )

            assert delta.added_reactions == ["thumbs_up"]
            assert cached_message.reactions["thumbs_up"] == 2  # Count incremented
