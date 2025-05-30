import base64
import pytest

from core.events.models.outgoing_events import (
    OutgoingAttachmentInfo,
    SendMessageData,
    EditMessageData,
    DeleteMessageData,
    ReactionData,
    FetchHistoryData,
    FetchAttachmentData,
    PinStatusData,
    SendMessageEvent,
    EditMessageEvent,
    DeleteMessageEvent,
    AddReactionEvent,
    RemoveReactionEvent,
    FetchHistoryEvent,
    FetchAttachmentEvent,
    PinMessageEvent,
    UnpinMessageEvent
)
from core.events.builders.outgoing_event_builder import OutgoingEventBuilder

class TestOutgoingEventBuilder:
    """Tests for the OutgoingEventBuilder class."""

    @pytest.fixture
    def event_builder(self):
        """Fixture for creating a test event builder."""
        return OutgoingEventBuilder()

    @pytest.fixture
    def sample_attachment(self):
        """Fixture for a sample attachment."""
        return {
            "file_name": "test.txt",
            "content": base64.b64encode(b"Hello World").decode('utf-8')
        }

    @pytest.fixture
    def sample_send_message_data(self, sample_attachment):
        """Fixture for sample send message data."""
        return {
            "event_type": "send_message",
            "data": {
                "conversation_id": "conv_123",
                "text": "Hello, world!",
                "attachments": [sample_attachment],
                "thread_id": "thread_123",
                "mentions": ["user_123", "user_456"]
            }
        }

    @pytest.fixture
    def sample_edit_message_data(self):
        """Fixture for sample edit message data."""
        return {
            "event_type": "edit_message",
            "data": {
                "conversation_id": "conv_123",
                "message_id": "msg_456",
                "text": "Edited message"
            }
        }

    @pytest.fixture
    def sample_delete_message_data(self):
        """Fixture for sample delete message data."""
        return {
            "event_type": "delete_message",
            "data": {
                "conversation_id": "conv_123",
                "message_id": "msg_456"
            }
        }

    @pytest.fixture
    def sample_add_reaction_data(self):
        """Fixture for sample add reaction data."""
        return {
            "event_type": "add_reaction",
            "data": {
                "conversation_id": "conv_123",
                "message_id": "msg_456",
                "emoji": "+1"
            }
        }

    @pytest.fixture
    def sample_remove_reaction_data(self):
        """Fixture for sample remove reaction data."""
        return {
            "event_type": "remove_reaction",
            "data": {
                "conversation_id": "conv_123",
                "message_id": "msg_456",
                "emoji": "+1"
            }
        }

    @pytest.fixture
    def sample_fetch_history_data(self):
        """Fixture for sample fetch history data."""
        return {
            "event_type": "fetch_history",
            "data": {
                "conversation_id": "conv_123",
                "limit": 10,
                "before": 1620000000000
            }
        }

    @pytest.fixture
    def sample_fetch_attachment_data(self):
        """Fixture for sample fetch attachment data."""
        return {
            "event_type": "fetch_attachment",
            "data": {
                "attachment_id": "att_789"
            }
        }

    @pytest.fixture
    def sample_pin_message_data(self):
        """Fixture for sample pin message data."""
        return {
            "event_type": "pin_message",
            "data": {
                "conversation_id": "conv_123",
                "message_id": "msg_456"
            }
        }

    @pytest.fixture
    def sample_unpin_message_data(self):
        """Fixture for sample unpin message data."""
        return {
            "event_type": "unpin_message",
            "data": {
                "conversation_id": "conv_123",
                "message_id": "msg_456"
            }
        }

    def test_build_send_message(self, event_builder, sample_send_message_data, sample_attachment):
        """Test building a send_message event."""
        event = event_builder.build(sample_send_message_data)

        assert isinstance(event, SendMessageEvent)
        assert event.event_type == "send_message"
        assert isinstance(event.data, SendMessageData)
        assert event.data.conversation_id == sample_send_message_data["data"]["conversation_id"]
        assert event.data.text == sample_send_message_data["data"]["text"]
        assert event.data.thread_id == sample_send_message_data["data"]["thread_id"]
        assert event.data.mentions == sample_send_message_data["data"]["mentions"]

        # Verify attachments
        assert len(event.data.attachments) == 1
        assert isinstance(event.data.attachments[0], OutgoingAttachmentInfo)
        assert event.data.attachments[0].file_name == sample_attachment["file_name"]
        assert event.data.attachments[0].content == sample_attachment["content"]

        # Verify custom_name is None if not provided
        assert event.data.custom_name is None

    def test_build_send_message_with_custom_name(self, event_builder, sample_send_message_data):
        """Test building a send_message event with custom_name."""
        custom_name = "Bot Name"
        sample_send_message_data["data"]["custom_name"] = custom_name
        event = event_builder.build(sample_send_message_data)

        assert event.data.custom_name == custom_name

    def test_build_send_message_without_attachments(self, event_builder, sample_send_message_data):
        """Test building a send_message event without attachments."""
        sample_send_message_data["data"].pop("attachments", None)

        event = event_builder.build(sample_send_message_data)

        assert len(event.data.attachments) == 0

    def test_build_edit_message(self, event_builder, sample_edit_message_data):
        """Test building an edit_message event."""
        event = event_builder.build(sample_edit_message_data)

        assert isinstance(event, EditMessageEvent)
        assert event.event_type == "edit_message"
        assert isinstance(event.data, EditMessageData)
        assert event.data.conversation_id == sample_edit_message_data["data"]["conversation_id"]
        assert event.data.message_id == sample_edit_message_data["data"]["message_id"]
        assert event.data.text == sample_edit_message_data["data"]["text"]

    def test_build_delete_message(self, event_builder, sample_delete_message_data):
        """Test building a delete_message event."""
        event = event_builder.build(sample_delete_message_data)

        assert isinstance(event, DeleteMessageEvent)
        assert event.event_type == "delete_message"
        assert isinstance(event.data, DeleteMessageData)
        assert event.data.conversation_id == sample_delete_message_data["data"]["conversation_id"]
        assert event.data.message_id == sample_delete_message_data["data"]["message_id"]

    def test_build_add_reaction(self, event_builder, sample_add_reaction_data):
        """Test building an add_reaction event."""
        event = event_builder.build(sample_add_reaction_data)

        assert isinstance(event, AddReactionEvent)
        assert event.event_type == "add_reaction"
        assert isinstance(event.data, ReactionData)
        assert event.data.conversation_id == sample_add_reaction_data["data"]["conversation_id"]
        assert event.data.message_id == sample_add_reaction_data["data"]["message_id"]
        assert event.data.emoji == sample_add_reaction_data["data"]["emoji"]

    def test_build_remove_reaction(self, event_builder, sample_remove_reaction_data):
        """Test building a remove_reaction event."""
        event = event_builder.build(sample_remove_reaction_data)

        assert isinstance(event, RemoveReactionEvent)
        assert event.event_type == "remove_reaction"
        assert isinstance(event.data, ReactionData)
        assert event.data.conversation_id == sample_remove_reaction_data["data"]["conversation_id"]
        assert event.data.message_id == sample_remove_reaction_data["data"]["message_id"]
        assert event.data.emoji == sample_remove_reaction_data["data"]["emoji"]

    def test_build_fetch_history(self, event_builder, sample_fetch_history_data):
        """Test building a fetch_history event."""
        event = event_builder.build(sample_fetch_history_data)

        assert isinstance(event, FetchHistoryEvent)
        assert event.event_type == "fetch_history"
        assert isinstance(event.data, FetchHistoryData)
        assert event.data.conversation_id == sample_fetch_history_data["data"]["conversation_id"]
        assert event.data.limit == sample_fetch_history_data["data"]["limit"]
        assert event.data.before == sample_fetch_history_data["data"]["before"]
        assert event.data.after is None  # Not provided in sample data

    def test_build_fetch_history_with_after(self, event_builder, sample_fetch_history_data):
        """Test building a fetch_history event with after parameter."""
        after_timestamp = 1610000000000
        sample_fetch_history_data["data"]["after"] = after_timestamp
        event = event_builder.build(sample_fetch_history_data)

        assert event.data.after == after_timestamp

    def test_build_fetch_attachment(self, event_builder, sample_fetch_attachment_data):
        """Test building a fetch_attachment event."""
        event = event_builder.build(sample_fetch_attachment_data)

        assert isinstance(event, FetchAttachmentEvent)
        assert event.event_type == "fetch_attachment"
        assert isinstance(event.data, FetchAttachmentData)
        assert event.data.attachment_id == sample_fetch_attachment_data["data"]["attachment_id"]

    def test_build_pin_message(self, event_builder, sample_pin_message_data):
        """Test building a pin_message event."""
        event = event_builder.build(sample_pin_message_data)

        assert isinstance(event, PinMessageEvent)
        assert event.event_type == "pin_message"
        assert isinstance(event.data, PinStatusData)
        assert event.data.conversation_id == sample_pin_message_data["data"]["conversation_id"]
        assert event.data.message_id == sample_pin_message_data["data"]["message_id"]

    def test_build_unpin_message(self, event_builder, sample_unpin_message_data):
        """Test building an unpin_message event."""
        event = event_builder.build(sample_unpin_message_data)

        assert isinstance(event, UnpinMessageEvent)
        assert event.event_type == "unpin_message"
        assert isinstance(event.data, PinStatusData)
        assert event.data.conversation_id == sample_unpin_message_data["data"]["conversation_id"]
        assert event.data.message_id == sample_unpin_message_data["data"]["message_id"]

    def test_unknown_event_type(self, event_builder):
        """Test handling of unknown event types."""
        with pytest.raises(ValueError, match=f"Unknown event type"):
            event_builder.build({
                "event_type": "invalid_event",
                "data": {}
            })

    def test_missing_event_type(self, event_builder):
        """Test handling of missing event type."""
        with pytest.raises(ValueError, match="Unknown event type: None"):
            event_builder.build({
                "data": {
                    "conversation_id": "conv_123",
                    "text": "Hello, world!"
                }
            })

    def test_missing_required_fields(self, event_builder):
        """Test validation of required fields."""
        with pytest.raises(ValueError):
            event_builder.build({
                "event_type": "send_message",
                "data": {
                    # Missing conversation_id
                    "text": "Hello, world!"
                }
            })

    def test_extra_fields_ignored(self, event_builder):
        """Test that extra fields in the data are ignored."""
        event = event_builder.build({
            "event_type": "send_message",
            "data": {
                "conversation_id": "conv_123",
                "text": "Hello, world!",
                "extra_field": "should be ignored"
            }
        })

        # Event should be built successfully
        assert isinstance(event, SendMessageEvent)
        # Extra field should not be in the validated data
        assert not hasattr(event.data, "extra_field")

    def test_model_validation(self, event_builder, sample_send_message_data):
        """Test that events validate properly and can be converted to dict."""
        event = event_builder.build(sample_send_message_data)

        # Test that the model can be converted to dict
        event_dict = event.model_dump()

        assert isinstance(event_dict, dict)
        assert event_dict["event_type"] == "send_message"
        assert "data" in event_dict
        assert event_dict["data"]["conversation_id"] == sample_send_message_data["data"]["conversation_id"]
