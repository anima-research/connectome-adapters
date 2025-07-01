import pytest
from unittest.mock import MagicMock, patch

from src.adapters.zulip_adapter.conversation.reaction_handler import ReactionHandler
from src.core.cache.message_cache import CachedMessage
from src.core.conversation.base_data_classes import ConversationDelta
from src.core.utils.emoji_converter import EmojiConverter

class TestReactionHandler:
    """Tests for the Zulip ReactionHandler class"""

    @pytest.fixture
    def standard_conversation_id(self):
        """Create a standard conversation ID"""
        return "zulip_wWrMhAlqbPvWgzzVrBvL"

    @pytest.fixture
    def cached_message(self, standard_conversation_id):
        """Create a cached message with initial reactions"""
        cached_msg = CachedMessage(
            message_id="123",
            conversation_id=standard_conversation_id,
            text="Test message",
            sender_id="789",
            sender_name="Test User",
            timestamp=1234567890000,
            edit_timestamp=None,
            edited=False,
            is_from_bot=False,
            thread_id = None,
            reactions={"thumbs_up": 1}  # Initial reaction
        )
        return cached_msg

    @pytest.fixture
    def delta(self, standard_conversation_id):
        """Create a ConversationDelta object"""
        return ConversationDelta(
            conversation_id=standard_conversation_id,
            message_id="123"
        )

    def test_update_message_reactions_add(self, cached_message, delta):
        """Test updating delta when a reaction is added"""
        message = {
            "op": "add",
            "emoji_name": "heart",
            "emoji_code": "2764",
            "reaction_type": "unicode_emoji"
        }

        instance_mock = MagicMock()
        instance_mock.platform_specific_to_standard.return_value = "red_heart"

        with patch.object(EmojiConverter, "_instance", instance_mock):
            ReactionHandler.update_message_reactions(message, cached_message, delta)

            assert len(delta.added_reactions) == 1
            assert delta.added_reactions[0] == "red_heart"
            assert "red_heart" in cached_message.reactions
            assert cached_message.reactions["red_heart"] == 1

    def test_update_message_reactions_remove(self, cached_message, delta):
        """Test updating delta when a reaction is removed"""
        message = {
            "op": "remove",
            "emoji_name": "+1",
            "emoji_code": "1f44d",
            "reaction_type": "unicode_emoji"
        }

        instance_mock = MagicMock()
        instance_mock.platform_specific_to_standard.return_value = "thumbs_up"

        with patch.object(EmojiConverter, "_instance", instance_mock):
            ReactionHandler.update_message_reactions(message, cached_message, delta)

            assert len(delta.removed_reactions) == 1
            assert delta.removed_reactions[0] == "thumbs_up"
            assert "thumbs_up" not in cached_message.reactions  # Should be removed
