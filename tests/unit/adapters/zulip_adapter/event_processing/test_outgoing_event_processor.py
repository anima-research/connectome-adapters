import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import emoji

from src.adapters.zulip_adapter.event_processing.outgoing_event_processor import OutgoingEventProcessor
from src.core.events.processors.base_outgoing_event_processor import OutgoingEventType
from src.core.utils.emoji_converter import EmojiConverter

class TestOutgoingEventProcessor:
    """Tests for the OutgoingEventProcessor class"""

    @pytest.fixture
    def zulip_client_mock(self):
        """Create a mocked Zulip client"""
        client = AsyncMock()
        client.client = MagicMock()
        client.send_message = MagicMock(return_value={"result": "success"})
        client.update_message = MagicMock(return_value={"result": "success"})
        client.call_endpoint = MagicMock(return_value={"result": "success"})
        client.add_reaction = MagicMock(return_value={"result": "success"})
        client.remove_reaction = MagicMock(return_value={"result": "success"})
        return client

    @pytest.fixture
    def standard_private_conversation_id(self):
        """Create a mocked standard private conversation"""
        return "zulip_wWrMhAlqbPvWgzzVrBvL"

    @pytest.fixture
    def private_conversation_mock(self, standard_private_conversation_id):
        """Create a mocked private conversation"""
        conversation = MagicMock()
        conversation.conversation_type = "private"
        conversation.emails.return_value = ["test@example.com", "test@example.com"]
        conversation.platform_conversation_id = "123_456"
        conversation.conversation_id = standard_private_conversation_id
        return conversation

    @pytest.fixture
    def standard_stream_conversation_id(self):
        """Create a mocked standard stream conversation"""
        return "zulip_wYODBtgv3KAQUYQU7mMB"

    @pytest.fixture
    def stream_conversation_mock(self, standard_stream_conversation_id):
        """Create a mocked stream conversation"""
        conversation = MagicMock()
        conversation.conversation_type = "stream"
        conversation.stream_id = "789"
        conversation.stream_name = "test-stream"
        conversation.stream_topic = "Some topic"
        conversation.platform_conversation_id = "789/Some topic"
        conversation.conversation_id = standard_stream_conversation_id
        return conversation

    @pytest.fixture
    def conversation_manager_mock(self,
                                  private_conversation_mock,
                                  stream_conversation_mock,
                                  standard_private_conversation_id,
                                  standard_stream_conversation_id):
        """Create a mocked conversation manager"""
        manager = AsyncMock()

        def get_conversation_side_effect(conversation_id):
            if conversation_id == standard_private_conversation_id:
                return private_conversation_mock
            elif conversation_id == standard_stream_conversation_id:
                return stream_conversation_mock
            return None

        manager.get_conversation = MagicMock(side_effect=get_conversation_side_effect)
        manager.add_to_conversation = AsyncMock()
        manager.update_conversation = AsyncMock()
        manager.delete_from_conversation = AsyncMock()
        manager.get_message = AsyncMock()
        return manager

    @pytest.fixture
    def uploader_mock(self):
        """Create a mocked uploader"""
        uploader = AsyncMock()
        uploader.upload_file = AsyncMock(return_value={"uri": "test-uri"})
        return uploader

    @pytest.fixture
    def processor(self,
                  zulip_config,
                  zulip_client_mock,
                  conversation_manager_mock,
                  uploader_mock,
                  rate_limiter_mock):
        """Create a ZulipOutgoingEventProcessor with mocked dependencies"""
        processor = OutgoingEventProcessor(zulip_config, zulip_client_mock, conversation_manager_mock)
        processor.rate_limiter = rate_limiter_mock
        processor.uploader = uploader_mock
        return processor

    class TestSendMessage:
        """Tests for the send_message method"""

        @pytest.mark.asyncio
        async def test_send_message_private_success(self,
                                                    processor,
                                                    zulip_client_mock,
                                                    standard_private_conversation_id):
            """Test sending a private message successfully"""
            event_data = {
                "event_type": OutgoingEventType.SEND_MESSAGE,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "text": "Hello, world!"
                }
            }

            with patch("asyncio.sleep"):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is True

            zulip_client_mock.send_message.assert_called_once_with({
                "type": "private",
                "to": ["test@example.com", "test@example.com"],
                "content": "Hello, world!",
                "subject": None
            })

        @pytest.mark.asyncio
        async def test_send_message_stream_success(self,
                                                    processor,
                                                    zulip_client_mock,
                                                    standard_stream_conversation_id):
            """Test sending a stream message successfully"""
            event_data = {
                "event_type": OutgoingEventType.SEND_MESSAGE,
                "data": {
                    "conversation_id": standard_stream_conversation_id,
                    "text": "Hello, stream!"
                }
            }

            with patch("asyncio.sleep"):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is True

            zulip_client_mock.send_message.assert_called_once_with({
                "type": "stream",
                "to": "test-stream",
                "content": "Hello, stream!",
                "subject": "Some topic"
            })

        @pytest.mark.asyncio
        async def test_send_message_long_text(self,
                                              processor,
                                              zulip_client_mock,
                                              standard_private_conversation_id):
            """Test sending a message with text longer than max length"""
            event_data = {
                "event_type": OutgoingEventType.SEND_MESSAGE,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "text": "This is a sentence. " * 10
                }
            }

            with patch("asyncio.sleep"):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is True
            assert zulip_client_mock.send_message.call_count > 1

        @pytest.mark.asyncio
        async def test_send_message_missing_required_fields(self,
                                                            processor,
                                                            standard_private_conversation_id):
            """Test sending a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.SEND_MESSAGE,
                "data": {"text": "Hello"}
            })
            assert response["request_completed"] is False

            # Missing text
            response = await processor.process_event({
                "event_type": OutgoingEventType.SEND_MESSAGE,
                "data": {"conversation_id": standard_private_conversation_id}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_send_message_api_failure(self,
                                                processor,
                                                zulip_client_mock,
                                                standard_private_conversation_id):
            """Test sending a message when API fails"""
            zulip_client_mock.send_message.return_value = {"result": "error", "msg": "Test error"}
            event_data = {
                "event_type": OutgoingEventType.SEND_MESSAGE,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "text": "Hello, world!"
                }
            }

            response = await processor.process_event(event_data)
            assert response["request_completed"] is False

    class TestEditMessage:
        """Tests for the edit_message method"""

        @pytest.mark.asyncio
        async def test_edit_message_success(self,
                                            processor,
                                            zulip_client_mock,
                                            standard_private_conversation_id):
            """Test successfully editing a message"""
            event_data = {
                "event_type": OutgoingEventType.EDIT_MESSAGE,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "message_id": "789",
                    "text": "Updated text"
                }
            }
            response = await processor.process_event(event_data)

            assert response["request_completed"] is True
            zulip_client_mock.update_message.assert_called_once_with({
                "message_id": 789,  # Should be converted to int
                "content": "Updated text"
            })

        @pytest.mark.asyncio
        async def test_edit_message_missing_required_fields(self,
                                                            processor,
                                                            standard_private_conversation_id):
            """Test editing a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.EDIT_MESSAGE,
                "data": {"message_id": "789", "text": "Hello"}
            })
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.EDIT_MESSAGE,
                "data": {"conversation_id": standard_private_conversation_id, "text": "Hello"}
            })
            assert response["request_completed"] is False

            # Missing text
            response = await processor.process_event({
                "event_type": OutgoingEventType.EDIT_MESSAGE,
                "data": {"conversation_id": standard_private_conversation_id, "message_id": "789"}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_edit_message_api_failure(self,
                                                processor,
                                                zulip_client_mock,
                                                standard_private_conversation_id):
            """Test editing a message when API fails"""
            zulip_client_mock.update_message.return_value = {"result": "error", "msg": "Test error"}
            event_data = {
                "event_type": OutgoingEventType.EDIT_MESSAGE,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "message_id": "789",
                    "text": "Updated text"
                }
            }
            response = await processor.process_event(event_data)

            assert response["request_completed"] is False

    class TestDeleteMessage:
        """Tests for the delete_message method"""

        @pytest.mark.asyncio
        async def test_delete_message_success(self,
                                              processor,
                                              zulip_client_mock,
                                              standard_private_conversation_id):
            """Test successfully deleting a message"""
            event_data = {
                "event_type": OutgoingEventType.DELETE_MESSAGE,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "message_id": "789"
                }
            }
            response = await processor.process_event(event_data)

            assert response["request_completed"] is True
            zulip_client_mock.call_endpoint.assert_called_once_with("messages/789",method="DELETE")

        @pytest.mark.asyncio
        async def test_delete_message_missing_required_fields(self,
                                                              processor,
                                                              standard_private_conversation_id):
            """Test deleting a message with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.DELETE_MESSAGE,
                "data": {"message_id": "789"}
            })
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.DELETE_MESSAGE,
                "data": {"conversation_id": standard_private_conversation_id}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_delete_message_api_failure(self,
                                                  processor,
                                                  zulip_client_mock,
                                                  standard_private_conversation_id):
            """Test deleting a message when API fails"""
            zulip_client_mock.call_endpoint.return_value = {"result": "error", "msg": "Test error"}
            event_data = {
                "event_type": OutgoingEventType.DELETE_MESSAGE,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "message_id": "789"
                }
            }
            response = await processor.process_event(event_data)
            assert response["request_completed"] is False

    class TestReactions:
        """Tests for reaction-related methods"""

        @pytest.mark.asyncio
        async def test_add_reaction_success(self,
                                             processor,
                                             zulip_client_mock,
                                             standard_private_conversation_id):
            """Test successfully adding a reaction"""
            event_data = {
                "event_type": OutgoingEventType.ADD_REACTION,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "message_id": "789",
                    "emoji": "thumbs_up"
                }
            }

            instance_mock = MagicMock()
            instance_mock.standard_to_platform_specific.return_value = "+1"

            with patch.object(EmojiConverter, "_instance", instance_mock):
                response = await processor.process_event(event_data)

                assert response["request_completed"] is True
                zulip_client_mock.add_reaction.assert_called_once_with({
                    "message_id": 789,
                    "emoji_name": "+1"
                })

        @pytest.mark.asyncio
        async def test_add_reaction_missing_required_fields(self,
                                                             processor,
                                                             standard_private_conversation_id):
            """Test adding a reaction with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.ADD_REACTION,
                "data": {"message_id": "789", "emoji": "+1"}
            })
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.ADD_REACTION,
                "data": {"conversation_id": standard_private_conversation_id, "emoji": "+1"}
            })
            assert response["request_completed"] is False

            # Missing emoji
            response = await processor.process_event({
                "event_type": OutgoingEventType.ADD_REACTION,
                "data": {"conversation_id": standard_private_conversation_id, "message_id": "789"}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_add_reaction_api_failure(self,
                                                processor,
                                                zulip_client_mock,
                                                standard_private_conversation_id):
            """Test adding a reaction when API fails"""
            zulip_client_mock.add_reaction.return_value = {"result": "error", "msg": "Test error"}
            event_data = {
                "event_type": OutgoingEventType.ADD_REACTION,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "message_id": "789",
                    "emoji": "thumbs_up"
                }
            }
            instance_mock = MagicMock()
            instance_mock.standard_to_platform_specific.return_value = "+1"

            with patch.object(EmojiConverter, "_instance", instance_mock):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_remove_reaction_success(self,
                                               processor,
                                               zulip_client_mock,
                                               standard_private_conversation_id):
            """Test successfully removing a reaction"""
            event_data = {
                "event_type": OutgoingEventType.REMOVE_REACTION,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "message_id": "789",
                    "emoji": "thumbs_up"
                }
            }

            instance_mock = MagicMock()
            instance_mock.standard_to_platform_specific.return_value = "+1"

            with patch.object(EmojiConverter, "_instance", instance_mock):
                response = await processor.process_event(event_data)

                assert response["request_completed"] is True
                zulip_client_mock.remove_reaction.assert_called_once_with({
                    "message_id": 789,
                    "emoji_name": "+1"
                })

        @pytest.mark.asyncio
        async def test_remove_reaction_missing_required_fields(self,
                                                                processor,
                                                                standard_private_conversation_id):
            """Test removing a reaction with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.REMOVE_REACTION,
                "data": {"message_id": "789", "emoji": "+1"}
            })
            assert response["request_completed"] is False

            # Missing message_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.REMOVE_REACTION,
                "data": {"conversation_id": standard_private_conversation_id, "emoji": "+1"}
            })
            assert response["request_completed"] is False

            # Missing emoji
            response = await processor.process_event({
                "event_type": OutgoingEventType.REMOVE_REACTION,
                "data": {"conversation_id": standard_private_conversation_id, "message_id": "789"}
            })
            assert response["request_completed"] is False

        @pytest.mark.asyncio
        async def test_remove_reaction_api_failure(self,
                                                    processor,
                                                    zulip_client_mock,
                                                    standard_private_conversation_id):
            """Test removing a reaction when API fails"""
            zulip_client_mock.remove_reaction.return_value = {"result": "error", "msg": "Test error"}
            event_data = {
                "event_type": OutgoingEventType.REMOVE_REACTION,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                    "message_id": "789",
                    "emoji": "red_heart"
                }
            }
            instance_mock = MagicMock()
            instance_mock.standard_to_platform_specific.return_value = "red_heart"

            with patch.object(EmojiConverter, "_instance", instance_mock):
                response = await processor.process_event(event_data)
                assert response["request_completed"] is False

    class TestSendTypingIndicator:
        """Tests for send_typing_indicator method"""

        @pytest.mark.asyncio
        async def test_send_typing_indicator_success(self,
                                             processor,
                                             zulip_client_mock,
                                             standard_private_conversation_id):
            """Test successfully adding a reaction"""
            event_data = {
                "event_type": OutgoingEventType.SEND_TYPING_INDICATOR,
                "data": {
                    "conversation_id": standard_private_conversation_id,
                }
            }

            response = await processor.process_event(event_data)
            assert response["request_completed"] is True
            zulip_client_mock.call_endpoint.call_count == 2

        @pytest.mark.asyncio
        async def test_send_typing_indicator_missing_required_fields(self, processor):
            """Test adding a reaction with missing required fields"""
            # Missing conversation_id
            response = await processor.process_event({
                "event_type": OutgoingEventType.SEND_TYPING_INDICATOR, "data": {}
            })
            assert response["request_completed"] is False

    class TestFetchHistory:
        """Tests for the fetch_history method"""

        @pytest.mark.asyncio
        async def test_fetch_history_missing_parameters(self,
                                                        processor,
                                                        standard_private_conversation_id):
            """Test fetching history with missing parameters"""
            event_data = {
                "event_type": OutgoingEventType.FETCH_HISTORY,
                "data": {"conversation_id": standard_private_conversation_id}
            }
            result = await processor.process_event(event_data)
            assert result["request_completed"] is False

    class TestHelperMethods:
        """Tests for helper methods"""

        def test_check_api_request_failure(self, processor):
            """Test API response checking with failure result"""
            with pytest.raises(Exception):
                processor._check_api_request_success(
                    {"result": "error", "msg": "Test error"},
                    "test operation"
                )

        def test_check_api_request_none(self, processor):
            """Test API response checking with None result"""
            with pytest.raises(Exception):
                processor._check_api_request_success(None, "test operation")

        def test_split_long_message_short(self, processor):
            """Test splitting a message that's already short enough"""
            text = "This is a short message."
            assert processor._split_long_message(text) == [text]

        def test_split_long_message_long(self, processor):
            """Test splitting a long message at sentence boundaries"""
            result = processor._split_long_message("First sentence. Second sentence. " * 100)

            assert len(result) > 1
            assert (result[-1].endswith(". ") or result[-1].endswith("."))
