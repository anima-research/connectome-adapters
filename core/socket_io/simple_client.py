import socketio
import asyncio
import logging

from typing import Optional

logging.basicConfig(level=logging.INFO)
sio = socketio.AsyncClient(logger=True)

@sio.event
async def connect():
    print("Connected to adapter")

@sio.event
async def disconnect():
    print("Disconnected from adapter")

@sio.event
async def bot_request(data):
    print("Message received")
    print(f"Data: {data}")

    #await asyncio.sleep(5)
    #await send_message(data.get("data").get("conversation_id"), "Hello, world!")
    #await asyncio.sleep(5)
    #await edit_message(data.get("data").get("conversation_id"), data.get("data").get("message_id"), "Hello, world! (edt)")
    #await asyncio.sleep(5)
    #await delete_message(data.get("data").get("conversation_id"), data.get("data").get("message_id"))
    #await asyncio.sleep(5)
    #await add_reaction(data.get("data").get("conversation_id"), data.get("data").get("message_id"), "👍")
    #await asyncio.sleep(5)
    #await remove_reaction(data.get("data").get("conversation_id"), data.get("data").get("message_id"), "👍")

@sio.event
async def request_queued(data):
    print("Request queued")
    print(f"Data: {data}")

@sio.event
async def request_success(data):
    print("Request success")
    print(f"Data: {data}")

@sio.event
async def request_failed(data):
    print("Request failed")
    print(f"Data: {data}")

async def send_message(conversation_id: str, text: str, thread_id: Optional[str] = None) -> None:
    """Send a message to a conversation

    Args:
        conversation_id: ID of the conversation (chat/group/channel)
        text: Message text content
        thread_ref: Optional thread reference (for replies)
    """
    try:
        data = {
            "event_type": "send_message",
            "data": {
                "conversation_id": conversation_id,
                "text": text,
                "attachments": [
                    #{
                    #    "attachment_type": "photo",
                    #    "file_path": "adapters/telegram_adapter/attachments/photo/tmp/234.png",
                    #    "size": 343929
                    #}
                ]
            }
        }

        if thread_id:
            data["data"]["thread_id"] = thread_id

        await sio.emit("bot_response", data)
        print(f"Sent message to conversation {conversation_id}")
    except Exception as e:
        print(f"Error sending message: {e}")

async def edit_message(conversation_id: str, message_id: str, new_text: str) -> None:
    """Edit a previously sent message

    Args:
        conversation_id: ID of the conversation
        message_id: ID of the message to edit
        new_text: New message text
    """
    try:
        data = {
            "event_type": "edit_message",
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "text": new_text
            }
        }

        await sio.emit("bot_response", data)
        print(f"Edited message {message_id}")
    except Exception as e:
        print(f"Error editing message: {e}")

async def delete_message(conversation_id: str, message_id: str) -> None:
    """Delete a message

    Args:
        conversation_id: ID of the conversation
        message_id: ID of the message to delete
    """
    try:
        data = {
            "event_type": "delete_message",
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id
            }
        }

        await sio.emit("bot_response", data)
        print(f"Deleted message {message_id}")
    except Exception as e:
        print(f"Error deleting message: {e}")

async def add_reaction(conversation_id: str, message_id: str, emoji: str) -> None:
    """Add a reaction to a message

    Args:
        conversation_id: ID of the conversation
        message_id: ID of the message to react to
        emoji: Emoji reaction
    """
    try:
        data = {
            "event_type": "add_reaction",
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "emoji": emoji
            }
        }

        await sio.emit("bot_response", data)
        print(f"Added reaction {emoji} to message {message_id}")
    except Exception as e:
        print(f"Error adding reaction: {e}")

async def remove_reaction(conversation_id: str, message_id: str, emoji: str) -> None:
    """Remove a reaction from a message

    Args:
        conversation_id: ID of the conversation
        message_id: ID of the message to react to
        emoji: Emoji reaction
    """
    try:
        data = {
            "event_type": "remove_reaction",
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "emoji": emoji
            }
        }

        await sio.emit("bot_response", data)
        print(f"Removed reaction {emoji} from message {message_id}")
    except Exception as e:
        print(f"Error removing reaction: {e}")

async def main():
    server_url = "http://127.0.0.1:8081"
    logging.info(f"Connecting to adapter at {server_url}")

    try:
        await sio.connect(server_url)
        await sio.wait()
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        if sio.connected:
            await sio.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
