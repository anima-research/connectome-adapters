import pytest
from unittest.mock import MagicMock, AsyncMock

from adapters.telegram_adapter.adapter.conversation.reaction_handler import ReactionHandler
from core.conversation.base_data_classes import ConversationDelta

class TestReactionHandler:
    """Tests for the ReactionHandler class"""

    @pytest.fixture
    def mock_reactions(self):
        """Create a mock Telethon MessageReactions object"""
        reactions = MagicMock()

        result1 = MagicMock()
        result1.reaction = MagicMock()
        result1.reaction.emoticon = "👍"
        result1.count = 2

        result2 = MagicMock()
        result2.reaction = MagicMock()
        result2.reaction.emoticon = "❤️"
        result2.count = 1

        reactions.results = [result1, result2]
        return reactions

    @pytest.fixture
    def mock_cached_message(self):
        """Create a mock cached message"""
        cached_msg = MagicMock()
        cached_msg.message_id = "123"
        cached_msg.text = "Test message"
        cached_msg.reactions = {"👍": 1}  # Initial reactions
        return cached_msg

    @pytest.mark.asyncio
    async def test_extract_reactions_normal(self, mock_reactions):
        """Test extracting reactions from a normal reactions object"""
        result = await ReactionHandler.extract_reactions(mock_reactions)

        assert isinstance(result, dict)
        assert len(result) == 2
        assert result["👍"] == 2
        assert result["❤️"] == 1

    @pytest.mark.asyncio
    async def test_extract_reactions_none(self):
        """Test extracting reactions when reactions is None"""
        result = await ReactionHandler.extract_reactions(None)

        assert isinstance(result, dict)
        assert len(result) == 0

    def test_get_added_reactions(self):
        """Test getting added reactions"""
        old_reactions = {"👍": 1, "❤️": 2}
        new_reactions = {"👍": 2, "❤️": 2, "🔥": 1}

        result = ReactionHandler.get_added_reactions(old_reactions, new_reactions)

        assert isinstance(result, list)
        assert len(result) == 2
        assert "👍" in result  # Count increased
        assert "🔥" in result  # New emoji
        assert "❤️" not in result  # Count unchanged

    def test_get_added_reactions_none_added(self):
        """Test getting added reactions when none were added"""
        old_reactions = {"👍": 2, "❤️": 1}
        new_reactions = {"👍": 1, "❤️": 1}  # Count decreased or stayed the same

        result = ReactionHandler.get_added_reactions(old_reactions, new_reactions)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_removed_reactions(self):
        """Test getting removed reactions"""
        old_reactions = {"👍": 2, "❤️": 1, "🔥": 1}
        new_reactions = {"👍": 1, "🔥": 0}  # ❤️ removed, 🔥 count set to 0

        result = ReactionHandler.get_removed_reactions(old_reactions, new_reactions)

        assert isinstance(result, list)
        assert len(result) == 3
        assert "👍" in result  # Count decreased
        assert "❤️" in result  # Completely removed
        assert "🔥" in result  # Count set to 0

    def test_get_removed_reactions_none_removed(self):
        """Test getting removed reactions when none were removed"""
        old_reactions = {"👍": 1, "❤️": 1}
        new_reactions = {"👍": 1, "❤️": 2, "🔥": 1}  # Counts increased or stayed the same

        result = ReactionHandler.get_removed_reactions(old_reactions, new_reactions)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_update_message_reactions_added(self, mock_cached_message):
        """Test updating message reactions when reactions are added"""
        delta = ConversationDelta(conversation_id="123")
        new_reactions = {"👍": 2, "❤️": 1}  # Added ❤️ and increased 👍 count

        ReactionHandler.update_message_reactions(
            mock_cached_message, new_reactions, delta
        )

        assert len(delta.added_reactions) == 2
        assert "👍" in delta.added_reactions
        assert "❤️" in delta.added_reactions
        assert len(delta.removed_reactions) == 0
        assert mock_cached_message.reactions == new_reactions

    def test_update_message_reactions_removed(self, mock_cached_message):
        """Test updating message reactions when reactions are removed"""
        delta = ConversationDelta(conversation_id="123")
        mock_cached_message.reactions = {"👍": 2, "❤️": 1}  # Initial state
        new_reactions = {"👍": 1}  # Decreased 👍 count and removed ❤️

        ReactionHandler.update_message_reactions(
            mock_cached_message, new_reactions, delta
        )

        assert len(delta.added_reactions) == 0
        assert len(delta.removed_reactions) == 2
        assert "👍" in delta.removed_reactions  # Count decreased
        assert "❤️" in delta.removed_reactions  # Completely removed
        assert mock_cached_message.reactions == new_reactions
