import logging
import asyncio

from datetime import datetime
from typing import Optional, List, Union, Dict, Any

from telegram import Update, Message, InlineKeyboardMarkup, ReactionTypeEmoji
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.error import TimedOut, NetworkError, TelegramError

from config import Config
from conversation_tracker import ConversationTracker, ConversationInfo
from message_cache import MessageCache, CachedMessage

class TelegramBot:
    ADAPTER_VERSION = "0.1.0"  # Our adapter version
    TESTED_WITH_API = "8.0"    # Telegram Bot API version we've tested with

    def __init__(self, socketio_server=None):
        self.config = Config().get_instance()
        self.application = Application.builder().token(self.config.get_token()).build()
        self.running = False
        self.initialized = False
        self.message_cache = MessageCache()
        self.conversation_tracker = ConversationTracker(self.message_cache)
        self.socketio_server = socketio_server

        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("privacy", self._handle_privacy))
        self.application.add_handler(CommandHandler("deletedata", self._handle_delete_data))
        self.application.add_handler(CommandHandler("exportdata", self._handle_export_data))
        self.application.add_handler(CommandHandler("correct", self._handle_correct))
        self.application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, self._handle_message))
        self.application.add_error_handler(self._error_handler)

        self.welcomed_users = set()
        self.welcomed_chats = set()

    async def _print_api_compatibility(self):
        """Print the API version"""
        try:
            result = await self.application.bot.get_me()
            logging.info(f"Connected to Telegram")
            logging.info(f"Adapter version {self.ADAPTER_VERSION}, tested with Telegram Bot API {self.TESTED_WITH_API}")
        except Exception as e:
            logging.warning(f"Could not verify API compatibility: {e}")

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        await self._send_welcome_message(update.message.chat, update.effective_user)

    async def _handle_privacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /privacy command"""
        conversation = update.message.chat
        user = update.effective_user

        if conversation.type == 'private':
            retention_days = self.config.get_setting("privacy.retention_direct_messages")
        else:
            retention_days = self.config.get_setting("privacy.retention_group_messages")

        policy_url = self.config.get_setting("privacy.policy_url")

        privacy_text = (
            f"🔐 *Privacy Information*\n\n"
            f"I store messages for {retention_days} days to provide my services.\n"
            f"You can request deletion of your data using /deletedata.\n"
            f"For our full privacy policy, visit: {policy_url}"
        )

        await self.send_message(conversation.id, privacy_text, parse_mode="Markdown")

    async def _handle_delete_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /delete_my_data command"""
        user = update.effective_user

        deleted = await self._delete_user_data(user.id)

        if deleted:
            await self.send_message(
                update.message.chat.id,
                f"✅ Your data has been deleted. Any new messages will be subject to our privacy policy.",
                for_caching = False
            )
        else:
            await self.send_message(
                update.message.chat.id,
                f"ℹ️ No data found to delete for your user.",
                for_caching = False
            )

    async def _delete_user_data(self, user_id: int) -> bool:
        """Delete all data for a specific user"""
        user_id = str(user_id)
        deleted_anything = False

        if hasattr(self, 'message_cache'):
            deleted_count = await self.message_cache.delete_user_data(user_id)
            if deleted_count > 0:
                deleted_anything = True
                logging.info(f"Deleted {deleted_count} messages for user {user_id}")

        if user_id in self.welcomed_users:
            self.welcomed_users.remove(user_id)
            deleted_anything = True

        return deleted_anything

    async def _send_welcome_message(self, chat, user) -> None:
        """Send appropriate welcome message based on chat type"""
        user_id = str(user.id) if user else None
        chat_id = str(chat.id)

        try:
            bot_name = self.application.bot.username or "Bot"

            if chat.type == 'private':
                retention = self.config.get_setting("privacy.retention_direct_messages")
                template = self.config.get_setting("privacy.welcome_message_direct")

                if user_id:
                    self.welcomed_users.add(user_id)
            else:
                retention = self.config.get_setting("privacy.retention_group_messages")
                template = self.config.get_setting("privacy.welcome_message_group")

                self.welcomed_chats.add(chat_id)

            policy_url = self.config.get_setting("privacy.policy_url")
            welcome_text = template.format(
                bot_name=bot_name,
                retention_direct_messages=retention,
                retention_group_messages=retention,
                policy_url=policy_url
            )

            await self.send_message(chat.id, welcome_text)
            logging.info(f"Sent welcome message to {'user '+user_id if chat.type == 'private' else 'chat '+chat_id}")
        except Exception as e:
            logging.error(f"Error sending welcome message: {e}")

    async def _handle_export_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /export_my_data command"""
        user = update.effective_user
        conversation = update.message.chat

        await self.send_message(
            conversation.id,
            "Preparing your data export. This may take a moment..."
        )

        # Always export only data from the current conversation
        user_data = await self._get_user_data_for_export(user.id, conversation.id)

        if not user_data or not user_data["conversations"]:
            await self.send_message(
                conversation.id,
                "No data found to export in this chat. This may be because your data has been deleted or has expired due to our retention policy."
            )
            return

        import json
        export_text = json.dumps(user_data, indent=2, default=str)

        if len(export_text) > 4000:  # Telegram message size limit
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp:
                temp_path = temp.name
                temp.write(export_text.encode('utf-8'))

            await self.application.bot.send_document(
                chat_id=conversation.id,
                document=open(temp_path, 'rb'),
                filename=f"chat_export_{conversation.id}.json",
                caption="Here is your data export for this chat."
            )

            import os
            os.unlink(temp_path)
        else:
            await self.send_message(
                conversation.id,
                f"Here is your data export for this chat:\n```json\n{export_text}\n```",
                parse_mode="Markdown"
            )

    async def _get_user_data_for_export(self, user_id: int, conversation_id: int) -> Dict:
        """Get user data from a specific conversation

        Args:
            user_id: The user ID to export data for
            conversation_id: The conversation to export from

        Returns:
            Dict containing the user's data
        """
        user_id_str = str(user_id)
        conv_id_str = str(conversation_id)

        result = {
            "user_id": user_id_str,
            "conversation_id": conv_id_str,
            "export_date": datetime.now().isoformat(),
            "conversations": {}
        }

        if conv_id_str not in self.message_cache.messages:
            return result

        messages = self.message_cache.messages[conv_id_str]
        conv_info = self.conversation_tracker.get_conversation_info(conv_id_str)
        conv_name = self.conversation_tracker.get_conversation_display_name(conv_id_str)

        user_messages = [
            {
                "message_id": msg.message_id,
                "timestamp": msg.timestamp.isoformat(),
                "text": msg.text,
                "in_thread": bool(msg.thread_id),
                "thread_id": msg.thread_id,
                "is_reply": bool(msg.reply_to_message_id),
                "reply_to": msg.reply_to_message_id
            }
            for msg_id, msg in messages.items()
            if msg.sender_id == user_id_str
        ]

        if user_messages:
            result["conversations"][conv_id_str] = {
                "name": conv_name,
                "type": conv_info.conversation_type if conv_info else "unknown",
                "messages": user_messages
            }

        return result

    async def _handle_correct(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /correct command for data rectification"""
        args = context.args
        if not args or len(args) < 2:
            await self.send_message(
                update.message.chat.id,
                "To correct a message, use the format: /correct message_id New corrected text\n"
                "For example: /correct 123 This is the corrected version of my message."
            )
            return

        user = update.effective_user
        conversation = update.message.chat

        try:
            message_id = args[0]
            corrected_text = " ".join(args[1:])
            success = await self._correct_message_in_cache(user.id, message_id, corrected_text)

            if success:
                await self.send_message(
                    conversation.id,
                    f"✅ Your message has been corrected. The corrected version will be used in future exports and processing."
                )
            else:
                await self.send_message(
                    conversation.id,
                    f"❌ Message not found or you're not the author of this message. Please check the message ID and try again."
                )
        except Exception as e:
            logging.error(f"Error correcting message: {e}")
            await self.send_message(
                conversation.id,
                "There was an error processing your correction request. Please try again later."
            )

    async def _correct_message_in_cache(self, user_id: int, message_id: str, corrected_text: str) -> bool:
        """Correct a message in the cache

        Returns:
            bool: True if message was found and corrected, False otherwise
        """
        user_id_str = str(user_id)

        for conv_id, messages in self.message_cache.messages.items():
            if message_id in messages and messages[message_id].sender_id == user_id_str:
                messages[message_id].text = f"{corrected_text} [Corrected]"
                logging.info(f"Message {message_id} corrected by user {user_id}")
                return True

        return False

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages and update chat tracking"""
        try:
            logging.error(f"Received update: {update}")
            conversation_info = await self.conversation_tracker.update_conversation_from_message(update)

            user = update.effective_user
            conversation = update.message.chat
            user_id = str(user.id) if user else None
            conversation_id = str(conversation.id)

            # Check for group creation or bot added to group
            is_new_group = False
            if hasattr(update.message, 'group_chat_created') and update.message.group_chat_created:
                is_new_group = True
            elif hasattr(update.message, 'new_chat_members'):
                for member in update.message.new_chat_members:
                    if member.id == self.application.bot.id:
                        is_new_group = True
                        break

            if conversation.type == 'private':
                needs_welcome = user_id and user_id not in self.welcomed_users
            else:
                needs_welcome = conversation_id not in self.welcomed_chats or is_new_group

            if needs_welcome:
                await self._send_welcome_message(conversation, user)

            if update.message:
                await self._process_message(update.message, conversation_info)
            elif update.edited_message:
                await self._process_edited_message(update.edited_message, conversation_info)
            elif update.channel_post:
                await self._process_channel_post(update.channel_post, conversation_info)
            elif update.edited_channel_post:
                await self._process_edited_channel_post(update.edited_channel_post, conversation_info)
            elif update.message_reaction:
                await self._process_reaction(update.message_reaction, conversation_info)
            elif update.chat_member:
                await self._process_chat_member_update(update.chat_member, conversation_info)

            if self.socketio_server and update.message:
                message_data = {
                    "message_id": update.message.message_id,
                    "conversation_id": update.message.chat_id,
                    "text": update.message.text if hasattr(update.message, "text") else None,
                    "from_user": update.message.from_user.id if update.message.from_user else None
                }
                await self.socketio_server.broadcast_message(message_data)
        except Exception as e:
            logging.error(f"Error processing update: {e}", exc_info=True)

    async def _process_message(self, message: Message, conversation_info: Optional[ConversationInfo]) -> None:
        conversation = message.chat

        if conversation.type == 'private':
            await self.send_message(
                chat_id=conversation.id,
                text="Please, stay on the line"
            )
        elif self._is_bot_mentioned(message) or self._is_command_for_bot(message):
            await self.send_message(
                chat_id=conversation.id,
                text="Please, stay on the line",
                reply_to_message_id=message.message_id
            )

    async def _process_edited_message(self, message: Message, conversation_info: Optional[ConversationInfo]) -> None:
        """Process an edited message"""
        user = message.from_user
        conversation = message.chat

        logging.info(f"Edited message from {user.username or 'Unknown'} "
                    f"in {conversation.type} {conversation.id}")

    async def _process_channel_post(self, message: Message, conversation_info: Optional[ConversationInfo]) -> None:
        """Process a channel post"""
        conversation = message.chat

        logging.info(f"Channel post in {conversation.title or conversation.id}")

    async def _process_edited_channel_post(self, message: Message, conversation_info: Optional[ConversationInfo]) -> None:
        """Process an edited channel post"""
        conversation = message.chat

        logging.info(f"Edited channel post in {conversation.title or conversation.id}")

    async def _process_reaction(self, reaction, conversation_info: Optional[ConversationInfo]) -> None:
        """Process a message reaction update"""
        logging.info(f"Reaction update in chat {reaction.chat.id}")

    async def _process_chat_member_update(self, chat_member_update, conversation_info: Optional[ConversationInfo]) -> None:
        """Process a chat member update"""
        logging.info(f"Member update in chat {chat_member_update.chat.id}")

    def _is_bot_mentioned(self, message: Message) -> bool:
        """Check if the bot is mentioned in the message or it's a reply to the bot"""
        if message.entities:
            bot_username = self.application.bot.username
            for entity in message.entities:
                if entity.type == 'mention':
                    start = entity.offset
                    end = entity.offset + entity.length
                    mention = message.text[start:end]
                    if mention == f"@{bot_username}":
                        return True

        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == self.application.bot.id:
                logging.info(f"Message is a reply to our bot")
                return True

        return False

    def _is_command_for_bot(self, message: Message) -> bool:
        """Check if the message contains a command for this bot"""
        if not message.entities:
            return False

        for entity in message.entities:
            if entity.type == 'bot_command':
                # In private chats, all commands are for this bot
                if message.chat.type == 'private':
                    return True

                # In groups, check if command is specifically for this bot
                if message.text:
                    start = entity.offset
                    end = entity.offset + entity.length
                    command = message.text[start:end]

                    # Check for commands like /start@my_bot_username
                    bot_username = self.application.bot.username
                    if f"@{bot_username}" in command:
                        return True

        return False

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the dispatcher"""
        logging.error(f"Exception while handling an update: {context.error}")

        if isinstance(context.error, TimedOut):
            logging.warning("Request timed out")
        elif isinstance(context.error, NetworkError):
            logging.warning(f"Network error: {context.error}")

    async def start(self) -> None:
        """Start the bot with retry logic for network issues"""
        self.running = True
        logging.debug("Starting bot...")

        for attempt in range(1, self.config.get_setting("max_retries") + 1):
            try:
                logging.debug(f"Initialization attempt {attempt}")
                await self.application.initialize()
                await self.application.start()
                await self._print_api_compatibility()
                await self.application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=[
                        "message",
                        "edited_message",
                        "channel_post",
                        "edited_channel_post",
                        "message_reaction",
                        "message_reaction_count",
                        "poll",
                        "poll_answer",
                        "my_chat_member",
                        "chat_member",
                        "chat_join_request"
                    ]
                )

                self.initialized = True
                logging.info("Bot started successfully.")
                return
            except (TimedOut, NetworkError) as e:
                logging.error(f"Network error during startup (attempt {attempt}): {e}")
                if attempt < self.config.get_setting("max_retries"):
                    await asyncio.sleep(self.config.get_setting("retry_delay"))
                else:
                    logging.error("Max retries reached. Could not start the bot.")
                    raise
            except Exception as e:
                logging.error(f"Error starting bot: {e}")
                raise

        self.maintenance_task = asyncio.create_task(self._cache_maintenance_loop())

    async def stop(self) -> None:
        """Stop the bot"""
        if self.running:
            self.running = False
            if self.initialized:
                try:
                    await self.application.updater.stop()
                    await self.application.stop()
                    await self.application.shutdown()
                except Exception as e:
                    logging.error(f"Error stopping bot: {e}")
            logging.info("Bot stopped")

    async def send_message(self, chat_id: Union[int, str], text: str,
                           reply_to_message_id: Optional[int] = None,
                           for_caching = True,
                           **kwargs) -> Optional[Message]:
        """Send a text message to a chat."""
        try:
            message = await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                **kwargs
            )

            logging.info(f"Message sent to {chat_id}")

            if for_caching:
                await self.conversation_tracker.record_bot_message(message, reply_to_message_id)

            return message
        except TelegramError as e:
            logging.error(f"Failed to send message: {e}")
            return None

    async def edit_message(self, chat_id: Union[int, str], message_id: int,
                           new_text: str,
                           parse_mode: Optional[str] = None,
                           reply_markup: Optional[InlineKeyboardMarkup] = None) -> Optional[Message]:
        """
        Edit a message's text.

        Args:
            chat_id: Unique identifier for the target chat
            message_id: Identifier of the message to edit
            new_text: New text for the message
            parse_mode: Mode for parsing entities (None, 'Markdown', or 'HTML')
            reply_markup: Additional interface options (inline keyboard, etc)

        Returns:
            Message object if successful, None otherwise
        """
        try:
            message = await self.application.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=new_text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            logging.debug(f"Message {message_id} edited in chat {chat_id}")
            return message
        except TelegramError as e:
            logging.error(f"Failed to edit message: {e}")
            return None

    async def delete_message(self, chat_id: Union[int, str], message_id: int) -> bool:
        """
        Delete a message.

        Args:
            chat_id: Unique identifier for the target chat
            message_id: Identifier of the message to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            success = await self.application.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id
            )
            if success:
                logging.debug(f"Message {message_id} deleted from chat {chat_id}")
            return success
        except TelegramError as e:
            logging.error(f"Failed to delete message: {e}")
            return False

    async def add_reaction(self, chat_id: Union[int, str], message_id: int,
                           emoji: str) -> bool:
        """
        Add a reaction to a message.

        Args:
            chat_id: Unique identifier for the target chat
            message_id: Identifier of the message to react to
            emoji: Emoji to use as reaction

        Returns:
            True if successful, False otherwise
        """
        try:
            reaction = ReactionTypeEmoji(emoji=emoji)
            success = await self.application.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[reaction]
            )
            if success:
                logging.debug(f"Reaction {emoji} added to message {message_id} in chat {chat_id}")
            return success
        except TelegramError as e:
            logging.error(f"Failed to add reaction: {e}")
            return False

    async def remove_reaction(self, chat_id: Union[int, str], message_id: int) -> bool:
        """
        Remove all reactions from a message.

        Args:
            chat_id: Unique identifier for the target chat
            message_id: Identifier of the message to remove reactions from

        Returns:
            True if successful, False otherwise
        """
        try:
            # Passing an empty list removes all reactions
            success = await self.application.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[]
            )
            if success:
                logging.debug(f"Reactions removed from message {message_id} in chat {chat_id}")
            return success
        except TelegramError as e:
            logging.error(f"Failed to remove reactions: {e}")
            return False

    async def get_message_history(self, conversation_id: str, limit: int = 50) -> List[CachedMessage]:
        """Get recent messages from a conversation (standard method required by spec)"""
        return await self.message_cache.get_message_history(conversation_id, limit)

    async def get_thread_messages(self, conversation_id: str, thread_id: str, limit: int = 50) -> List[CachedMessage]:
        """Get messages from a specific thread"""
        return await self.message_cache.get_thread_messages(conversation_id, thread_id, limit)

    async def get_message(self, conversation_id: str, message_id: str) -> Optional[CachedMessage]:
        """Get a specific message by ID"""
        return await self.message_cache.get_message_by_id(conversation_id, message_id)

    async def handle_llm_response(self, data: Dict[str, Any]) -> None:
        """Handle response from an LLM client"""
        try:
            conversation_id = data.get("conversation_id")
            text = data.get("text")
            reply_to_message_id = data.get("reply_to_message_id")

            if not conversation_id or not text:
                logging.error(f"Invalid LLM response format: {data}")
                return

            await self.send_message(
                chat_id=conversation_id,
                text=text,
                reply_to_message_id=reply_to_message_id
            )

            logging.info(f"Sent LLM response to chat {conversation_id}")
        except Exception as e:
            logging.error(f"Error handling LLM response: {e}", exc_info=True)
