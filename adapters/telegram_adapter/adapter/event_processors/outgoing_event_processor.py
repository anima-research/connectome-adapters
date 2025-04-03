import asyncio
import emoji
import json
import logging
import os
import telethon

from enum import Enum
from telethon import functions
from telethon.tl.types import ReactionEmoji
from typing import Any, Dict, List, Optional, Union

from adapters.telegram_adapter.adapter.attachment_loaders.uploader import Uploader
from adapters.telegram_adapter.adapter.conversation.manager import Manager
from adapters.telegram_adapter.adapter.event_processors.history_fetcher import HistoryFetcher

from core.event_processors.base_outgoing_event_processor import BaseOutgoingEventProcessor
from core.utils.config import Config

class OutgoingEventProcessor(BaseOutgoingEventProcessor):
    """Processes events from socket.io and sends them to Telegram"""

    def __init__(self, config: Config, client: Any, conversation_manager: Manager):
        """Initialize the socket.io events processor

        Args:
            config: Config instance
            client: Telethon client instance
            conversation_manager: Conversation manager for tracking message history
        """
        super().__init__(config, client)
        self.conversation_manager = conversation_manager
        self.uploader = Uploader(self.config, self.client)

    async def _send_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to a chat

        Args:
            data: Event data containing conversation_id, text, and optional attachments

        Returns:
            Dict[str, Any]: Dictionary containing the status and message_ids
        """
        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        entity = await self._get_entity(conversation_id)
        message_ids = []
        reply_to_message_id = data.get("thread_id", None)

        for message in self._split_long_message(data.get("text")):
            await self.rate_limiter.limit_request("message", conversation_id)

            message = await self.client.send_message(
                entity=entity, message=message, reply_to=reply_to_message_id
            )
            if hasattr(message, "id"):
                message_ids.append(str(message.id))

            await self.conversation_manager.add_to_conversation({"message": message})

        attachments = data.get("attachments", [])
        for attachment in attachments:
            await self.rate_limiter.limit_request("message", conversation_id)
            attachment_info = await self.uploader.upload_attachment(entity, attachment)

            if attachment_info and attachment_info.get("message"):
                message = attachment_info["message"]
                if hasattr(message, "id"):
                    message_ids.append(str(message.id))
                del attachment_info["message"]

                await self.conversation_manager.add_to_conversation({
                    "message": message,
                    "attachments": [attachment_info]
                })

        logging.info(f"Message sent to conversation {conversation_id}")
        return {"request_completed": True, "message_ids": message_ids}

    async def _edit_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Edit a message

        Args:
            data: Event data containing conversation_id, message_id, and text

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        entity = await self._get_entity(conversation_id)

        await self.rate_limiter.limit_request("edit_message", conversation_id)
        await self.conversation_manager.update_conversation({
            "event_type": "edited_message",
            "message": await self.client.edit_message(
                entity=entity,
                message=int(data.get("message_id")),
                text=data.get("text")
            )
        })

        logging.info(f"Message edited in conversation {conversation_id}")
        return {"request_completed": True}

    async def _delete_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a message

        Args:
            data: Event data containing conversation_id and message_id

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        entity = await self._get_entity(self._format_conversation_id(data["conversation_id"]))
        await self.rate_limiter.limit_request("delete_message", data["conversation_id"])
        messages = await self.client.delete_messages(entity=entity, message_ids=[(int(data["message_id"]))])

        if messages:
            await self.conversation_manager.delete_from_conversation(
                outgoing_event={
                    "deleted_ids": [data["message_id"]],
                    "conversation_id": data["conversation_id"]
                }
            )

        logging.info(f"Message deleted in conversation {data['conversation_id']}")
        return {"request_completed": True}

    async def _add_reaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a reaction to a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        entity = await self._get_entity(conversation_id)
        emoji_symbol = emoji.emojize(f":{data['emoji']}:")

        if not emoji_symbol or emoji_symbol == f":{data['emoji']}:":
            logging.error(f"Python library emoji does not support this emoji: {data['emoji']}")
            return {"request_completed": False}

        await self.rate_limiter.limit_request("add_reaction", conversation_id)
        await self.conversation_manager.update_conversation({
            "event_type": "edited_message",
            "message": await self.client(
                functions.messages.SendReactionRequest(
                    peer=entity,
                    msg_id=int(data.get("message_id")),
                    reaction=[ReactionEmoji(emoticon=emoji_symbol)]
                )
            )
        })

        logging.info(f"Reaction added to message in conversation {conversation_id}")
        return {"request_completed": True}

    async def _remove_reaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove a specific reaction from a message

        Args:
            data: Event data containing conversation_id, message_id, and emoji

        Returns:
            Dict[str, Any]: Dictionary containing the status
        """
        conversation_id = self._format_conversation_id(data.get("conversation_id"))
        entity = await self._get_entity(conversation_id)
        emoji_symbol = emoji.emojize(f":{data['emoji']}:")

        if not emoji_symbol or emoji_symbol == f":{data['emoji']}:":
            logging.error(f"Python library emoji does not support this emoji: {data['emoji']}")
            return {"request_completed": False}

        await self.rate_limiter.limit_request("get_messages", conversation_id)

        message_id = int(data.get("message_id"))
        old_message = await self.client.get_messages(entity, ids=message_id)
        old_reactions = getattr(old_message, "reactions", None) if old_message else None
        new_reactions = self._update_reactions_list(old_reactions, emoji_symbol)

        await self.rate_limiter.limit_request("remove_reaction", conversation_id)
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

        logging.info(f"Reaction removed from message in conversation {conversation_id}")
        return {"request_completed": True}

    async def _fetch_history(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch history of a conversation

        Args:
            data: Event data containing conversation_id,
                  before or after datetime as int (one of the two must be provided),
                  limit (optional, default is taken from config)

        Returns:
            Dict[str, Any]: Dictionary containing the status and history
        """
        before = data.get("before", None)
        after = data.get("after", None)

        if not before and not after:
            logging.error("No before or after datetime provided")
            return {"request_completed": False}

        history = await HistoryFetcher(
            self.config,
            self.client,
            self.conversation_manager,
            data["conversation_id"],
            before=before,
            after=after,
            history_limit=data.get("limit", None)
        ).fetch()

        return {"request_completed": True, "history": history}

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

    async def _get_entity(self, conversation_id: Union[str, int]) -> Any:
        """Get an entity from a conversation ID

        Args:
            conversation_id: The conversation ID

        Returns:
            The entity or raises an exception if not found
        """
        await self.rate_limiter.limit_request("get_entity")

        entity = await self.client.get_entity(conversation_id)
        if not entity:
            raise Exception(f"No entity found for conversation {conversation_id}")

        return entity
