import pytest
from datetime import datetime

from core.events.models.incoming_events import IncomingAttachmentInfo, SenderInfo
from core.events.models.request_events import (
    RequestEvent,
    FetchedAttachmentData,
    FetchedMessageData,
    HistoryData,
    SentMessageData,
    ReadFileData,
    ViewDirectoryData
)
from core.events.builders.request_event_builder import RequestEventBuilder

class TestRequestEventBuilder:
    """Tests for the RequestEventBuilder class."""

    @pytest.fixture
    def request_event_builder(self):
        """Fixture for a request event builder."""
        return RequestEventBuilder(adapter_type="test_adapter")

    @pytest.fixture
    def sample_attachment_info(self):
        """Fixture for sample attachment info."""
        return {
            "attachment_id": "att_456",
            "filename": "test_attachment_123.txt",
            "size": 12345,
            "content_type": "text/plain",
            "content": None,
            "url": "https://example.com/test_attachment_123.txt",
            "processable": True
        }

    @pytest.fixture
    def sample_message_data(self, sample_attachment_info):
        """Fixture for sample message data."""
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
            "attachments": [sample_attachment_info],
            "timestamp": int(datetime.now().timestamp() * 1000)
        }

    def test_initialization(self):
        """Test the initialization of the request event builder."""
        builder = RequestEventBuilder(adapter_type="telegram")
        assert builder.adapter_type == "telegram"

    def test_build_sent_message_data(self, request_event_builder):
        """Test building an event with SentMessageData."""
        internal_request_id = "internal_req_123"
        request_id = "req_123"
        message_ids = ["msg_456", "msg_789"]
        data = {"message_ids": message_ids}

        event = request_event_builder.build(request_id, internal_request_id, data)

        assert isinstance(event, RequestEvent)
        assert event.adapter_type == request_event_builder.adapter_type
        assert event.request_id == request_id
        assert event.internal_request_id == internal_request_id
        assert isinstance(event.data, SentMessageData)
        assert event.data.message_ids == message_ids

    def test_build_fetched_attachment_data(self, request_event_builder):
        """Test building an event with FetchedAttachmentData."""
        internal_request_id = "internal_req_456"
        request_id = "req_456"
        content = "base64encodedcontent"
        data = {"content": content}

        event = request_event_builder.build(request_id, internal_request_id, data)

        assert isinstance(event, RequestEvent)
        assert event.adapter_type == request_event_builder.adapter_type
        assert event.request_id == request_id
        assert event.internal_request_id == internal_request_id
        assert isinstance(event.data, FetchedAttachmentData)
        assert event.data.content == content

    def test_build_history_data(self, request_event_builder, sample_message_data, sample_attachment_info):
        """Test building an event with HistoryData."""
        internal_request_id = "internal_req_789"
        request_id = "req_789"
        data = {"history": [sample_message_data]}

        event = request_event_builder.build(request_id, internal_request_id, data)

        assert isinstance(event, RequestEvent)
        assert event.adapter_type == request_event_builder.adapter_type
        assert event.request_id == request_id
        assert event.internal_request_id == internal_request_id
        assert isinstance(event.data, HistoryData)
        assert len(event.data.history) == 1

        # Verify the history item
        history_item = event.data.history[0]
        assert isinstance(history_item, FetchedMessageData)
        assert history_item.message_id == sample_message_data["message_id"]
        assert history_item.conversation_id == sample_message_data["conversation_id"]
        assert history_item.text == sample_message_data["text"]
        assert history_item.thread_id == sample_message_data["thread_id"]
        assert history_item.timestamp == sample_message_data["timestamp"]

        # Verify sender
        assert isinstance(history_item.sender, SenderInfo)
        assert history_item.sender.user_id == sample_message_data["sender"]["user_id"]
        assert history_item.sender.display_name == sample_message_data["sender"]["display_name"]

        # Verify attachments
        assert len(history_item.attachments) == 1
        assert isinstance(history_item.attachments[0], IncomingAttachmentInfo)
        assert history_item.attachments[0].attachment_id == sample_attachment_info["attachment_id"]
        assert history_item.attachments[0].filename == sample_attachment_info["filename"]
        assert history_item.attachments[0].size == sample_attachment_info["size"]
        assert history_item.attachments[0].content_type == sample_attachment_info["content_type"]
        assert history_item.attachments[0].content == sample_attachment_info["content"]
        assert history_item.attachments[0].url == sample_attachment_info["url"]
        assert history_item.attachments[0].processable == sample_attachment_info["processable"]

    def test_build_history_data_multiple_messages(self, request_event_builder, sample_message_data):
        """Test building an event with HistoryData containing multiple messages."""
        internal_request_id = "internal_req_789"
        request_id = "req_789"

        # Create a second message with different data
        second_message = sample_message_data.copy()
        second_message["message_id"] = "msg_987"
        second_message["text"] = "Another message"

        data = {"history": [sample_message_data, second_message]}

        event = request_event_builder.build(request_id, internal_request_id, data)

        assert isinstance(event.data, HistoryData)
        assert len(event.data.history) == 2

        # Verify both messages
        assert event.data.history[0].message_id == sample_message_data["message_id"]
        assert event.data.history[1].message_id == second_message["message_id"]
        assert event.data.history[1].text == second_message["text"]

    def test_build_history_data_empty(self, request_event_builder):
        """Test building an event with empty HistoryData."""
        event = request_event_builder.build("req_789", "internal_req_789", {"history": []})

        assert isinstance(event.data, HistoryData)
        assert len(event.data.history) == 0

    def test_build_history_data_minimal_message(self, request_event_builder):
        """Test building history with minimal message data."""
        internal_request_id = "internal_req_789"
        request_id = "req_789"
        minimal_message = {
            "message_id": "msg_123",
            "conversation_id": "conv_456",
            "timestamp": int(datetime.now().timestamp() * 1000)
            # Missing optional fields
        }
        event = request_event_builder.build(
            request_id, internal_request_id, {"history": [minimal_message]}
        )

        assert isinstance(event.data, HistoryData)
        assert len(event.data.history) == 1

        # Verify defaults for missing fields
        history_item = event.data.history[0]
        assert history_item.message_id == minimal_message["message_id"]
        assert history_item.conversation_id == minimal_message["conversation_id"]
        assert history_item.text == ""  # Default
        assert history_item.thread_id is None  # Default
        assert len(history_item.attachments) == 0  # Default

        # Verify default sender
        assert history_item.sender.user_id == "Unknown"
        assert history_item.sender.display_name == "Unknown User"

    def test_build_read_file_data(self, request_event_builder):
        """Test building an event with ReadFileData."""
        file_content = "This is the content of the file\nWith multiple lines.\n"
        event = request_event_builder.build("req_123", "internal_req_123", {"file_content": file_content})

        assert isinstance(event.data, ReadFileData)
        assert event.data.file_content == file_content
        assert event.request_id == "req_123"
        assert event.internal_request_id == "internal_req_123"
        assert event.adapter_type == "test_adapter"

    def test_build_read_file_data_empty(self, request_event_builder):
        """Test building an event with empty ReadFileData."""
        event = request_event_builder.build("req_123", "internal_req_123", {"file_content": ""})

        assert isinstance(event.data, ReadFileData)
        assert event.data.file_content == ""
        assert event.request_id == "req_123"
        assert event.internal_request_id == "internal_req_123"

    def test_build_view_directory_data(self, request_event_builder):
        """Test building an event with ViewDirectoryData."""
        directories = ["dir1", "dir2", "dir3"]
        files = ["file1.txt", "file2.py", "file3.md"]

        event = request_event_builder.build(
            "req_456", "internal_req_456", {"directories": directories, "files": files}
        )

        assert isinstance(event.data, ViewDirectoryData)
        assert event.data.directories == directories
        assert event.data.files == files
        assert event.request_id == "req_456"
        assert event.internal_request_id == "internal_req_456"
        assert event.adapter_type == "test_adapter"

    def test_build_view_directory_data_empty(self, request_event_builder):
        """Test building an event with empty ViewDirectoryData."""
        event = request_event_builder.build(
            "req_456", "internal_req_456", {"directories": [], "files": []}
        )

        assert isinstance(event.data, ViewDirectoryData)
        assert len(event.data.directories) == 0
        assert len(event.data.files) == 0

    def test_build_with_empty_data(self, request_event_builder):
        """Test building an event with empty data."""
        internal_request_id = "internal_req_empty"
        request_id = "req_empty"
        event = request_event_builder.build(request_id, internal_request_id)

        assert isinstance(event, RequestEvent)
        assert event.adapter_type == request_event_builder.adapter_type
        assert event.request_id == request_id
        assert event.internal_request_id == internal_request_id
        assert event.data is None

    def test_build_with_unrecognized_data(self, request_event_builder):
        """Test building an event with unrecognized data."""
        internal_request_id = "internal_req_unknown"
        request_id = "req_unknown"
        data = {"unrecognized_field": "value"}
        event = request_event_builder.build(request_id, internal_request_id, data)

        assert isinstance(event, RequestEvent)
        assert event.adapter_type == request_event_builder.adapter_type
        assert event.request_id == request_id
        assert event.internal_request_id == internal_request_id
        assert event.data is None

    def test_model_validation(self, request_event_builder):
        """Test that built events validate properly and can be converted to dict."""
        internal_request_id = "internal_req_123"
        request_id = "req_123"
        message_ids = ["msg_456", "msg_789"]
        event = request_event_builder.build(
            request_id, internal_request_id, {"message_ids": message_ids}
        )

        # Test that the model can be converted to dict
        event_dict = event.model_dump()

        assert isinstance(event_dict, dict)
        assert event_dict["adapter_type"] == request_event_builder.adapter_type
        assert event_dict["request_id"] == request_id
        assert event_dict["internal_request_id"] == internal_request_id
        assert "data" in event_dict
        assert "message_ids" in event_dict["data"]
        assert event_dict["data"]["message_ids"] == message_ids
