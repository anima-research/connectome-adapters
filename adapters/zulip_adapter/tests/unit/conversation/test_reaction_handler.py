import pytest
from unittest.mock import MagicMock, patch

from adapters.zulip_adapter.adapter.conversation.reaction_handler import ReactionHandler
from core.cache.message_cache import CachedMessage
from core.conversation.base_data_classes import ConversationDelta

class TestReactionHandler:
    """Tests for the Zulip ReactionHandler class"""

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
            thread_id = None,
            reactions={"👍": 1}  # Initial reaction
        )
        return cached_msg

    @pytest.fixture
    def delta(self):
        """Create a ConversationDelta object"""
        return ConversationDelta(conversation_id="456", message_id="123")

    class TestEmojiConversion:
        """Tests for emoji conversion functionality"""

        def test_convert_emoji_code_to_symbol_unicode(self):
            """Test converting emoji code to Unicode symbol"""
            message = {
                "emoji_name": "thumbs_up",
                "emoji_code": "1f44d",
                "reaction_type": "unicode_emoji"
            }

            assert ReactionHandler.convert_emoji_code_to_symbol(message) == "👍"

        def test_convert_emoji_code_to_symbol_non_unicode(self):
            """Test converting non-Unicode emoji"""
            message = {
                "emoji_name": "custom_emoji",
                "emoji_code": "custom123",
                "reaction_type": "realm_emoji"  # Not unicode_emoji
            }

            assert ReactionHandler.convert_emoji_code_to_symbol(message) == "custom_emoji"

        def test_convert_emoji_code_to_symbol_invalid_code(self):
            """Test handling invalid emoji codes"""
            with patch("emoji.emojize", return_value=":invalid_emoji:"):
                message = {
                    "emoji_name": "invalid_emoji",
                    "emoji_code": "not_hex",  # Invalid hex code
                    "reaction_type": "unicode_emoji"
                }

                assert ReactionHandler.convert_emoji_code_to_symbol(message) == ":invalid_emoji:"

    class TestReactionManagement:
        """Tests for reaction addition and removal"""

        def test_add_reaction_new(self, cached_message):
            """Test adding a new reaction"""
            ReactionHandler.add_reaction(cached_message, "❤️")

            assert "❤️" in cached_message.reactions
            assert cached_message.reactions["❤️"] == 1
            assert cached_message.reactions["👍"] == 1  # Original reaction still present

        def test_add_reaction_existing(self, cached_message):
            """Test increasing count of an existing reaction"""
            ReactionHandler.add_reaction(cached_message, "👍")

            assert cached_message.reactions["👍"] == 2

        def test_remove_reaction_existing(self, cached_message):
            """Test removing an existing reaction"""
            ReactionHandler.remove_reaction(cached_message, "👍")

            assert "👍" not in cached_message.reactions  # Should be removed when count reaches 0

        def test_remove_reaction_multiple(self, cached_message):
            """Test decreasing count of a reaction with multiple occurrences"""
            cached_message.reactions["❤️"] = 2

            ReactionHandler.remove_reaction(cached_message, "❤️")

            assert "❤️" in cached_message.reactions
            assert cached_message.reactions["❤️"] == 1  # Count decreased but still present

        def test_remove_reaction_nonexistent(self, cached_message):
            """Test removing a reaction that doesn't exist"""
            initial_reactions = cached_message.reactions.copy()

            ReactionHandler.remove_reaction(cached_message, "🔥")

            assert cached_message.reactions == initial_reactions  # No change

    class TestUpdateMessageReactions:
        """Tests for the update_message_reactions method"""

        def test_update_message_reactions_add(self, cached_message, delta):
            """Test updating delta when a reaction is added"""
            message = {
                "op": "add",
                "emoji_name": "heart",
                "emoji_code": "2764",
                "reaction_type": "unicode_emoji"
            }

            with patch.object(ReactionHandler, "convert_emoji_code_to_symbol", return_value="❤️"):
                result = ReactionHandler.update_message_reactions(message, cached_message, delta)

            assert len(result.added_reactions) == 1
            assert result.added_reactions[0] == "❤️"
            assert "❤️" in cached_message.reactions
            assert cached_message.reactions["❤️"] == 1

        def test_update_message_reactions_remove(self, cached_message, delta):
            """Test updating delta when a reaction is removed"""
            message = {
                "op": "remove",
                "emoji_name": "thumbs_up",
                "emoji_code": "1f44d",
                "reaction_type": "unicode_emoji"
            }

            with patch.object(ReactionHandler, "convert_emoji_code_to_symbol", return_value="👍"):
                result = ReactionHandler.update_message_reactions(message, cached_message, delta)

            assert len(result.removed_reactions) == 1
            assert result.removed_reactions[0] == "👍"
            assert "👍" not in cached_message.reactions  # Should be removed
