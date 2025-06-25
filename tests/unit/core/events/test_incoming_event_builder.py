import pytest

from datetime import datetime
from pydantic import BaseModel
from unittest.mock import patch

from src.core.events.models.incoming_events import MessageReceivedData, MessageReceivedEvent
from src.core.events.builders.incoming_event_builder import IncomingEventBuilder

class TestIncomingEventBuilder:
    """Tests for the IncomingEventBuilder"""

    @pytest.fixture
    def event_builder(self):
        """Fixture for creating a test event builder."""
        return IncomingEventBuilder(
            adapter_type="test_adapter",
            adapter_name="test_instance",
            adapter_id="test_id"
        )

    @pytest.fixture
    def sample_attachment(self):
        """Fixture for a sample attachment."""
        return {
            "attachment_id": "test_attachment_123",
            "filename": "test_attachment_123.txt",
            "size": 12345,
            "content_type": "text/plain",
            "content": "base64encodedcontent",
            "url": "https://example.com/test_attachment_123.txt",
            "processable": True
        }

    @pytest.fixture
    def sample_message_delta(self, sample_attachment):
        """Fixture for a sample message delta."""
        return {
            "message_id": "msg_123",
            "conversation_id": "conv_456",
            "sender": {
                "user_id": "user_789",
                "display_name": "Test User"
            },
            "text": "Hello, world!",
            "thread_id": "thread_101",
            "is_direct_message": True,
            "attachments": [sample_attachment],
            "timestamp": int(datetime.now().timestamp()),
            "edit_timestamp": None,
            "edited": True,
            "mentions": ["user_101", "user_102"]
        }

    @pytest.fixture
    def sample_history(self, sample_message_delta):
        """Fixture for sample conversation history."""
        return [sample_message_delta]

    def test_initialization(self):
        """Test the correct initialization of the event builder."""
        builder = IncomingEventBuilder(
            adapter_type="telegram",
            adapter_name="telegram_bot",
            adapter_id="telegram_bot_id"
        )

        assert builder.adapter_type == "telegram"
        assert builder.adapter_name == "telegram_bot"
        assert builder.adapter_id == "telegram_bot_id"

    def test_conversation_started(self, event_builder):
        """Test conversation_started event creation."""
        delta = {
            "conversation_id": "conv_456",
            "conversation_name": "slackchannel",
            "server_name": "slackteam"
        }

        event = event_builder.conversation_started(delta)

        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "conversation_started"
        assert event["data"]["server_name"] == delta["server_name"]
        assert event["data"]["conversation_id"] == delta["conversation_id"]
        assert event["data"]["conversation_name"] == delta["conversation_name"]
        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id

    def test_message_received(self, event_builder, sample_message_delta):
        """Test message_received event creation."""
        event = event_builder.message_received(sample_message_delta)

        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "message_received"
        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert event["data"]["message_id"] == sample_message_delta["message_id"]
        assert event["data"]["conversation_id"] == sample_message_delta["conversation_id"]
        assert event["data"]["text"] == sample_message_delta["text"]
        assert event["data"]["thread_id"] == sample_message_delta["thread_id"]
        assert event["data"]["is_direct_message"] == sample_message_delta["is_direct_message"]
        assert event["data"]["mentions"] == sample_message_delta["mentions"]
        assert event["data"]["edit_timestamp"] == sample_message_delta["edit_timestamp"]
        assert event["data"]["edited"] == sample_message_delta["edited"]
        assert len(event["data"]["attachments"]) == 1

    def test_message_updated(self, event_builder, sample_message_delta, sample_attachment):
        """Test message_updated event creation."""
        event = event_builder.message_updated(sample_message_delta)

        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "message_updated"
        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert event["data"]["message_id"] == sample_message_delta["message_id"]
        assert event["data"]["conversation_id"] == sample_message_delta["conversation_id"]
        assert event["data"]["new_text"] == sample_message_delta["text"]
        assert event["data"]["mentions"] == sample_message_delta["mentions"]
        assert len(event["data"]["attachments"]) == 1

        attachment = event["data"]["attachments"][0]
        assert attachment["attachment_id"] == sample_attachment["attachment_id"]
        assert attachment["filename"] == sample_attachment["filename"]
        assert attachment["size"] == sample_attachment["size"]
        assert attachment["content_type"] == sample_attachment["content_type"]
        assert attachment["content"] == sample_attachment["content"]
        assert attachment["url"] == sample_attachment["url"]
        assert attachment["processable"] == sample_attachment["processable"]

    def test_message_deleted(self, event_builder):
        """Test message_deleted event creation."""
        message_id = "msg_123"
        conversation_id = "conv_456"

        event = event_builder.message_deleted(message_id, conversation_id)

        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "message_deleted"
        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert event["data"]["message_id"] == message_id
        assert event["data"]["conversation_id"] == conversation_id

    def test_message_deleted_with_int_ids(self, event_builder):
        """Test message_deleted with integer IDs."""
        message_id = 123
        conversation_id = 456

        event = event_builder.message_deleted(message_id, conversation_id)

        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert event["data"]["message_id"] == str(message_id)
        assert event["data"]["conversation_id"] == str(conversation_id)

    def test_reaction_update_added(self, event_builder):
        """Test reaction_added event creation."""
        delta = {
            "message_id": "msg_123",
            "conversation_id": "conv_456"
        }
        reaction = "+1"

        event = event_builder.reaction_update("reaction_added", delta, reaction)

        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "reaction_added"
        assert event["data"]["message_id"] == delta["message_id"]
        assert event["data"]["conversation_id"] == delta["conversation_id"]
        assert event["data"]["emoji"] == reaction

    def test_reaction_update_removed(self, event_builder):
        """Test reaction_removed event creation."""
        delta = {
            "message_id": "msg_123",
            "conversation_id": "conv_456"
        }
        reaction = "+1"

        event = event_builder.reaction_update("reaction_removed", delta, reaction)

        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "reaction_removed"
        assert event["data"]["message_id"] == delta["message_id"]
        assert event["data"]["conversation_id"] == delta["conversation_id"]
        assert event["data"]["emoji"] == reaction

    def test_reaction_update_invalid_type(self, event_builder):
        """Test reaction_update with invalid event type."""
        delta = {
            "message_id": "msg_123",
            "conversation_id": "conv_456"
        }
        reaction = "+1"

        with pytest.raises(ValueError, match="Unknown reaction event type: invalid_type"):
            event_builder.reaction_update("invalid_type", delta, reaction)

    def test_pin_status_update_pinned(self, event_builder):
        """Test message_pinned event creation."""
        delta = {
            "message_id": "msg_123",
            "conversation_id": "conv_456"
        }

        event = event_builder.pin_status_update("message_pinned", delta)

        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "message_pinned"
        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert event["data"]["message_id"] == delta["message_id"]
        assert event["data"]["conversation_id"] == delta["conversation_id"]

    def test_pin_status_update_unpinned(self, event_builder):
        """Test message_unpinned event creation."""
        delta = {
            "message_id": "msg_123",
            "conversation_id": "conv_456"
        }

        event = event_builder.pin_status_update("message_unpinned", delta)

        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "message_unpinned"
        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert event["data"]["message_id"] == delta["message_id"]
        assert event["data"]["conversation_id"] == delta["conversation_id"]

    def test_pin_status_update_invalid_type(self, event_builder):
        """Test pin_status_update with invalid event type."""
        delta = {
            "message_id": "msg_123",
            "conversation_id": "conv_456"
        }

        with pytest.raises(ValueError, match="Unknown pin status event type: invalid_type"):
            event_builder.pin_status_update("invalid_type", delta)

    def test_history_fetched(self, event_builder, sample_message_delta, sample_history):
        """Test history_fetched event creation."""
        delta = {"conversation_id": "conv_456"}

        event = event_builder.history_fetched(delta, sample_history)

        assert event["adapter_type"] == event_builder.adapter_type
        assert event["event_type"] == "history_fetched"
        assert event["data"]["conversation_id"] == delta["conversation_id"]
        assert event["data"]["adapter_name"] == event_builder.adapter_name
        assert event["data"]["adapter_id"] == event_builder.adapter_id
        assert len(event["data"]["history"]) == 1

        history_item = event["data"]["history"][0]
        assert history_item["message_id"] == sample_message_delta["message_id"]
        assert history_item["conversation_id"] == sample_message_delta["conversation_id"]
        assert history_item["text"] == sample_message_delta["text"]

    def test_event_model_validation(self, event_builder, sample_message_delta):
        """Test that events can be properly converted back to Pydantic models."""
        # Create event dictionary
        event_dict = event_builder.message_received(sample_message_delta)

        # Convert back to Pydantic model
        event_model = MessageReceivedEvent(**event_dict)

        # Verify that the model validates correctly
        assert event_model.adapter_type == event_builder.adapter_type
        assert event_model.event_type == "message_received"
        assert isinstance(event_model.data, MessageReceivedData)

    def test_event_invalid_data(self, event_builder, sample_message_delta):
        """Test event validation with invalid data."""
        # Create a valid event dictionary
        event_dict = event_builder.message_received(sample_message_delta)

        # Corrupt the event data
        event_dict["data"]["sender"] = None  # Should be a dict with user_id and display_name

        # Attempt to convert to Pydantic model should raise validation error
        with pytest.raises(ValueError):
            MessageReceivedEvent(**event_dict)

    def test_required_fields(self, event_builder):
        """Test validation of required fields."""
        # Missing required fields
        incomplete_delta = {
            "conversation_id": "conv_456",
            # Missing message_id
            "sender": {
                "user_id": "user_789",
                "display_name": "Test User"
            },
            "is_direct_message": True,
            "timestamp": int(datetime.now().timestamp())
        }

        # Should raise error due to missing message_id
        with pytest.raises(KeyError):
            event_builder.message_received(incomplete_delta)

    def test_attachment_optional_fields(self, event_builder):
        """Test that optional attachment fields are handled correctly."""
        # Attachment with only required fields
        minimal_attachment = {
            "attachment_id": "test_attachment_123",
            "attachment_type": "image",
            "filename": "test_attachment_123.jpg",
            "size": 12345,
            "content_type": "image/jpeg",
            "processable": True
            # Missing optional fields: url, content
        }

        message_delta = {
            "message_id": "msg_123",
            "conversation_id": "conv_456",
            "sender": {
                "user_id": "user_789",
                "display_name": "Test User"
            },
            "is_direct_message": True,
            "attachments": [minimal_attachment],
            "timestamp": int(datetime.now().timestamp()),
            "mentions": ["user_101", "user_102"]
        }

        # Should not raise error even with minimal attachment
        event = event_builder.message_received(message_delta)

        # Verify attachment fields
        attachment = event["data"]["attachments"][0]
        assert attachment["attachment_id"] == minimal_attachment["attachment_id"]
        assert attachment["filename"] == minimal_attachment["filename"]
        assert attachment["size"] == minimal_attachment["size"]
        assert attachment["content_type"] == minimal_attachment["content_type"]
        assert attachment["processable"] == minimal_attachment["processable"]
        assert attachment["url"] is None
        assert attachment["content"] is None
