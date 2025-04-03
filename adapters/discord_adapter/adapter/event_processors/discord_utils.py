import discord

from typing import Any, Optional

async def get_discord_channel(client: Any, conversation_id: str) -> Optional[Any]:
    """Get a Discord channel object

    Args:
        client: Discord client
        conversation_id: Conversation ID

    Returns:
        Discord channel object or None if not found
    """
    channel_id = int(conversation_id.split("/")[-1])
    channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)

    if not channel:
        raise Exception(f"Channel {channel_id} not found")

    return channel

def is_discord_service_message(message: Any) -> bool:
    """Check if a message is a service message

    Args:
        message: Discord message object

    Returns:
        True if the message is a service message, False otherwise
    """
    return (
        message.type != discord.MessageType.default and
        message.type != discord.MessageType.reply
    )
