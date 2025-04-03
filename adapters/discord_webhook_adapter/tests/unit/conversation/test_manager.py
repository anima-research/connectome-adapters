import pytest

from adapters.discord_webhook_adapter.adapter.conversation.data_classes import ConversationInfo
from adapters.discord_webhook_adapter.adapter.conversation.manager import Manager

class TestManager:
    """Tests for the Discord webhooks conversation manager class"""

    @pytest.fixture
    def manager(self, patch_config):
        """Create a Manager with mocked dependencies"""
        return Manager(patch_config)

    @pytest.fixture
    def mock_event(self):
        """Create a mock event with webhook info"""
        return {
            "id": "111222333",
            "conversation_id": "987654321/123456789",
            "webhook_url": "https://discord.com/api/webhooks/123456789/token",
            "webhook_name": "Test Bot"
        }

    @pytest.fixture
    def mock_delete_event(self):
        """Create a mock delete event"""
        return {
            "conversation_id": "987654321/123456789",
            "message_id": "111222333"
        }

    class TestAddToConversation:
        """Tests for add_to_conversation method"""

        def test_add_message_to_new_conversation(self, manager, mock_event):
            """Test adding a message to a new conversation"""
            assert len(manager.conversations) == 0

            manager.add_to_conversation(mock_event)

            assert "987654321/123456789" in manager.conversations

            conversation = manager.conversations["987654321/123456789"]
            assert conversation.conversation_id == "987654321/123456789"
            assert conversation.webhook_url == "https://discord.com/api/webhooks/123456789/token"
            assert conversation.webhook_name == "Test Bot"

            assert "111222333" in conversation.messages
            assert conversation.message_count == 1

        def test_add_message_to_existing_conversation(self, manager, mock_event):
            """Test adding a message to an existing conversation"""
            manager.conversations["987654321/123456789"] = ConversationInfo(
                conversation_id="987654321/123456789",
                webhook_url="https://discord.com/api/webhooks/123456789/token",
                webhook_name="Test Bot"
            )
            new_event = mock_event.copy()
            new_event["id"] = "444555666"

            manager.add_to_conversation(new_event)

            assert "444555666" in manager.conversations["987654321/123456789"].messages
            assert manager.conversations["987654321/123456789"].message_count == 1

    class TestDeleteFromConversation:
        """Tests for delete_from_conversation method"""

        def test_delete_message(self, manager, mock_delete_event):
            """Test deleting a message"""
            conversation = ConversationInfo(
                conversation_id="987654321/123456789",
                webhook_url="https://discord.com/api/webhooks/123456789/token",
                webhook_name="Test Bot"
            )
            conversation.messages.add("111222333")
            conversation.message_count = 1
            manager.conversations["987654321/123456789"] = conversation

            manager.delete_from_conversation(mock_delete_event)

            assert "111222333" not in conversation.messages
            assert conversation.message_count == 0

        def test_delete_last_message_removes_conversation(self, manager, mock_delete_event):
            """Test that deleting the last message removes the conversation"""
            conversation = ConversationInfo(
                conversation_id="987654321/123456789",
                webhook_url="https://discord.com/api/webhooks/123456789/token",
                webhook_name="Test Bot"
            )
            conversation.messages.add("111222333")
            conversation.message_count = 1
            manager.conversations["987654321/123456789"] = conversation

            manager.delete_from_conversation(mock_delete_event)

            assert "987654321/123456789" not in manager.conversations

    class TestGetOrCreateConversationInfo:
        """Tests for _get_or_create_conversation_info method"""

        def test_get_existing_conversation(self, manager, mock_event):
            """Test getting an existing conversation"""
            conversation = ConversationInfo(
                conversation_id="987654321/123456789",
                webhook_url="https://discord.com/api/webhooks/123456789/token",
                webhook_name="Test Bot"
            )
            manager.conversations["987654321/123456789"] = conversation

            assert manager._get_or_create_conversation_info(mock_event) is conversation

        def test_create_new_conversation(self, manager, mock_event):
            """Test creating a new conversation"""
            result = manager._get_or_create_conversation_info(mock_event)

            assert result is manager.conversations["987654321/123456789"]
            assert result.conversation_id == "987654321/123456789"
            assert result.webhook_url == "https://discord.com/api/webhooks/123456789/token"
            assert result.webhook_name == "Test Bot"
