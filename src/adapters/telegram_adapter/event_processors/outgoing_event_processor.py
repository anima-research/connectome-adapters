import asyncio
import emoji
import json
import logging
import os
import telethon

from pydantic import BaseModel
from telethon import functions
from telethon.tl.types import ReactionEmoji
from typing import Any, Dict, List, Union

from src.adapters.telegram_adapter.attachment_loaders.uploader import Uploader
from src.adapters.telegram_adapter.conversation.manager import Manager

from src.core.conversation.base_data_classes import UserInfo
from src.core.events.processors.base_outgoing_event_processor import BaseOutgoingEventProcessor
from src.core.utils.config import Config

class OutgoingEventProcessor(BaseOutgoingEventProcessor):
    """Processes events from socket.io and sends them to Telegram"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Telethon client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client, conversation_manager)
        self.uploader = Uploader(self.config, self.client)

    async def _send_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Send a message to a chat

        Args:
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dict[str, Any]: Dictionary containing the status and message_ids
        """
        entity = await self._get_entity(conversation_info)
        message_ids = []
        reply_to_message_id = None

        if data.thread_id:
            try:
                reply_to_message_id = int(data.thread_id)
            except ValueError:
                reply_to_message_id = None

        for message in self._split_long_message(
            self._mention_users(conversation_info, data.mentions, data.text)
        ):
            await self.rate_limiter.limit_request("message", data.conversation_id)

            message = await self.client.send_message(
                entity=entity, message=message, reply_to=reply_to_message_id
            )
            if hasattr(message, "id"):
                message_ids.append(str(message.id))

            await self.conversation_manager.add_to_conversation({"message": message})

        for attachment in data.attachments:
            await self.rate_limiter.limit_request("message", data.conversation_id)
            attachment_info = await self.uploader.upload_attachment(
                entity, attachment, reply_to=reply_to_message_id
            )

            if attachment_info and attachment_info.get("message"):
                message = attachment_info["message"]
                if hasattr(message, "id"):
                    message_ids.append(str(message.id))
                del attachment_info["message"]

                await self.conversation_manager.add_to_conversation({
                    "message": message,
                    "attachments": [attachment_info]
                })

        logging.info(f"Message sent to conversation {data.conversation_id}")
        return {"request_completed": True, "message_ids": message_ids}

    async def _edit_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Edit a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        entity = await self._get_entity(conversation_info)

        await self.rate_limiter.limit_request("edit_message", data.conversation_id)
        await self.conversation_manager.update_conversation({
            "event_type": "edited_message",
            "message": await self.client.edit_message(
                entity=entity,
                message=int(data.message_id),
                text=self._mention_users(conversation_info, data.mentions, data.text)
            )
        })

        logging.info(f"Message edited in conversation {data.conversation_id}")
        return {"request_completed": True}

    async def _delete_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Delete a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        entity = await self._get_entity(conversation_info)
        await self.rate_limiter.limit_request("delete_message", data.conversation_id)
        messages = await self.client.delete_messages(entity=entity, message_ids=[(int(data.message_id))])

        if messages:
            await self.conversation_manager.delete_from_conversation(
                outgoing_event={
                    "deleted_ids": [data.message_id],
                    "conversation_id": data.conversation_id
                }
            )

        logging.info(f"Message deleted in conversation {data.conversation_id}")
        return {"request_completed": True}

    async def _add_reaction(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Add a reaction to a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        entity = await self._get_entity(conversation_info)
        emoji_symbol = emoji.emojize(f":{data.emoji}:")

        if not emoji_symbol or emoji_symbol == f":{data.emoji}:":
            raise Exception(f"Python library emoji does not support this emoji: {data.emoji}")

        await self.rate_limiter.limit_request("add_reaction", data.conversation_id)
        await self.conversation_manager.update_conversation({
            "event_type": "edited_message",
            "message": await self.client(
                functions.messages.SendReactionRequest(
                    peer=entity,
                    msg_id=int(data.message_id),
                    reaction=[ReactionEmoji(emoticon=emoji_symbol)]
                )
            )
        })

        logging.info(f"Reaction added to message in conversation {data.conversation_id}")
        return {"request_completed": True}

    async def _remove_reaction(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Remove a specific reaction from a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        entity = await self._get_entity(conversation_info)
        emoji_symbol = emoji.emojize(f":{data.emoji}:")

        if not emoji_symbol or emoji_symbol == f":{data.emoji}:":
            raise Exception(f"Python library emoji does not support this emoji: {data.emoji}")

        await self.rate_limiter.limit_request("get_messages", data.conversation_id)

        message_id = int(data.message_id)
        old_message = await self.client.get_messages(entity, ids=message_id)
        old_reactions = getattr(old_message, "reactions", None) if old_message else None
        new_reactions = self._update_reactions_list(old_reactions, emoji_symbol)

        await self.rate_limiter.limit_request("remove_reaction", data.conversation_id)
        await self.conversation_manager.update_conversation({
            "event_type": "edited_message",
            "message": await self.client(
                functions.messages.SendReactionRequest(
                    peer=entity,
                    msg_id=message_id,
                    reaction=new_reactions
                )
            )
        })

        logging.info(f"Reaction removed from message in conversation {data.conversation_id}")
        return {"request_completed": True}

    async def _pin_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Pin a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        entity = await self._get_entity(conversation_info)

        await self.rate_limiter.limit_request("pin_message", data.conversation_id)
        message = await self.client(functions.messages.UpdatePinnedMessageRequest(
            peer=entity, id=int(data.message_id), silent=False
        ))

        if message:
            await self.conversation_manager.update_conversation({
                "event_type": "pinned_message",
                "message": {
                    "conversation_id": data.conversation_id,
                    "message_id": data.message_id
                }
            })

        logging.info(f"Message {data.message_id} pinned in conversation {data.conversation_id}")
        return {"request_completed": True}

    async def _unpin_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
        """Unpin a message

        Args:
            conversation_info: Conversation info
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        entity = await self._get_entity(conversation_info)
        await self.rate_limiter.limit_request("unpin_message", data.conversation_id)
        message = await self.client(functions.messages.UpdatePinnedMessageRequest(
            peer=entity, id=int(data.message_id), unpin=True
        ))

        if message:
            await self.conversation_manager.update_conversation({
                "event_type": "unpinned_message",
                "message": {
                    "conversation_id": data.conversation_id,
                    "message_id": data.message_id
                }
            })

        logging.info(f"Message {data.message_id} unpinned in conversation {data.conversation_id}")
        return {"request_completed": True}

    def _adapter_specific_mention_all(self) -> str:
        """Mention all users in a conversation

        Telegram doesn't have a native "mention all" feature,
        so we cannot mention all users in a conversation.
        """
        return ""

    def _adapter_specific_mention_user(self, user_info: UserInfo) -> str:
        """Mention a user in a conversation

        Args:
            user_info: User info

        Returns:
            str: Mention a user in a conversation

        Note:
            Telegram allows mentioning only users with username field set.
        """
        return f"@{user_info.username} " if user_info.username else ""

    def _format_conversation_id(self, conversation_id: Union[str, int]) -> Union[str, int]:
        """Format a conversation ID based on conversation type

        Args:
            conversation_id: The conversation ID to format

        Returns:
            The formatted conversation ID
        """
        try:
            return int(conversation_id)
        except (ValueError, TypeError):
            return conversation_id

    def _update_reactions_list(self, reactions, emoji_to_remove: str) -> List[Any]:
        """Remove a specific reaction from a message's reactions

        Args:
            reactions: Current reactions on the message
            emoji_to_remove: Emoji to remove

        Returns:
            List of reactions to keep
        """
        reaction_counts = {}
        reactions_to_add = []

        if reactions:
            for reaction in getattr(reactions, "results", []):
                emoticon = reaction.reaction.emoticon
                reaction_counts[emoticon] = reaction_counts.get(emoticon, 0) + 1

            if emoji_to_remove in reaction_counts:
                reaction_counts[emoji_to_remove] -= 1
                if reaction_counts[emoji_to_remove] <= 0:
                    del reaction_counts[emoji_to_remove]

        for emoji_type, count in reaction_counts.items():
            for _ in range(count):
                reactions_to_add.append(ReactionEmoji(emoticon=emoji_type))

        return reactions_to_add

    async def _get_entity(self, conversation_info: Any) -> Any:
        """Get an entity from a conversation ID

        Args:
            conversation_info: The conversation info

        Returns:
            The entity or raises an exception if not found
        """
        await self.rate_limiter.limit_request("get_entity")

        conversation_id = self._format_conversation_id(conversation_info.platform_conversation_id)
        entity = await self.client.get_entity(conversation_id)

        if not entity:
            raise Exception(f"No entity found for conversation {conversation_info.conversation_id}")

        return entity
