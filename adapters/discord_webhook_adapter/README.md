# Discord Webhook Adapter Documentation

### Purpose

The Discord Webhook Adapter provides a simplified, one-way integration with Discord that allows the connectome framework to send messages to Discord channels through webhooks. Unlike the full Discord adapter, this adapter:
* Focuses primarily on outgoing messages to Discord
* Uses Discord's webhook system rather than a full bot presence
* Doesn't require the bot to join conversations
* Provides a lightweight alternative for deployments where only message sending is needed
This adapter is ideal for use cases where the LLM only needs to respond in specific channels without tracking all channel activity.

### Discord.py and Webhook Integration

The adapter uses a hybrid approach combining:
* discord.py library: for initial setup and webhook creation
* aiohttp: for direct webhook interactions

The client maintains two critical components:
* Bot Connections. Traditional Discord bots used only for initial setup and webhook creation.
* HTTP Session. For direct webhook message delivery.

### Client Implementation

The webhook client manages both bot connections and webhook interactions:
```python
class DiscordWebhookClient:
    """Discord webhook client implementation"""

    def __init__(self, config: Config):
        # Initialize bot connections from configuration
        self.bot_configs = self.config.get_setting(
            "adapter", "bot_connections", default=[]
        )
        self.bots = {}

        # Create bot instances for each configuration
        for bot_config in self.bot_configs:
            intents = discord.Intents.default()
            intents.guilds = True
            self.bots[bot_config["bot_token"]] = commands.Bot(
                command_prefix='!',
                intents=intents,
                application_id=int(bot_config["application_id"])
            )

        # Initialize session and webhook storage
        self.session = None
        self.webhooks = {}
```

The client also provides methods to find or create webhooks for channels.
```python
async def get_or_create_webhook(self, conversation_id: str) -> Optional[Dict[str, Any]]:
    """Create a webhook in the specified channel if possible"""
    if conversation_id in self.webhooks:
        return self.webhooks[conversation_id]

    # If webhook doesn't exist, try to create one
    guild_id, channel_id = conversation_id.split("/")

    # Find a bot that has access to this guild/channel
    for bot_token in self.bots:
        guild = self.bots[bot_token].get_guild(int(guild_id))
        if not guild:
            continue

        channel = guild.get_channel(int(channel_id))
        if not channel:
            continue

        # Create webhook if permissions allow
        webhook = await channel.create_webhook(name="Connectome Bot")
        self.webhooks[conversation_id] = {
            "url": webhook.url,
            "name": webhook.name,
            "bot_token": bot_token
        }

        return self.webhooks[conversation_id]
```

The webhook adapter uses discord.py, which handles reconnection automatically, to manage webhooks. Meanwhile, the primary functionality of this adapter is sending webhook requests via HTTP. The aiohttp.ClientSession being used doesn't have built-in reconnection because webhook requests are stateless, each is a separate HTTP call. As a result, there's no persistent "connection" that needs to be maintained with webhooks. Failed webhook requests can simply be retried on the next attempt.

### Multi-Bot Support

The webhook adapter supports multiple bot tokens to access different Discord servers.

### Pre-configured Webhooks

It is possible to specify existing webhooks without needing to create them. This is useful for:
* Channels where the bot doesn't have MANAGE_WEBHOOKS permission
* Using existing webhooks created through Discord's UI
* Faster startup without webhook creation API calls

### Configuration

The Discord Webhook adapter is configured through a YAML file.
```yaml
adapter:
  adapter_type: "discord_webhook"
  bot_connections:
    - bot_token: "bot_token_1"            # Discord bot token for setup
      application_id: "application_id_1"  # Discord application ID
    - bot_token: "bot_token_2"            # Optional second bot token
      application_id: "application_id_2"  # Optional second application ID
    ...
  connection_check_interval: 300          # Seconds between connection health checks
  max_reconnect_attempts: 5               # Max number of attempts to reconnect if connection lost
  max_message_length: 1999                # Maximum message length (Discord limit: 2000)
  max_history_limit: 100                  # Maximum messages to fetch for history
  max_pagination_iterations: 10           # Maximum pagination iterations for history
  webhooks:                               # Pre-configured webhooks that can be unrelated to bots
    - conversation_id: "guild_id/channel_id"
      url: "webhook_url"
      name: "webhook_name"
    ....

attachments:
  storage_dir: "adapters/discord_webhook_adapter/attachments"  # Local storage directory
  max_file_size_mb: 8                                          # Maximum attachment size in MB
  max_attachments_per_message: 10                              # Maximum attachments per message

logging:
  logging_level: "info"               # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_file_path: "adapters/discord_webhook_adapter/logs/development.log"
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_log_size: 5242880               # Maximum log file size in bytes
  backup_count: 3                     # Number of log file backups to keep

rate_limit:
  global_rpm: 50                      # Global rate limit (requests per minute) for ALL requests
  per_conversation_rpm: 10            # Per-conversation rate limit
  message_rpm: 5                      # Message sending rate limit

socketio:
  host: "127.0.0.1"                   # Socket.IO server host
  port: 8083                          # Socket.IO server port
  cors_allowed_origins: "*"           # CORS allowed origins
```

### Discord webhook specific features

1) Conversation Mapping. Like the standard Discord adapter, conversations are identified using a composite ID formed from both the guild (server) ID and the channel ID: `guild_id/channel_id`. However, the webhook adapter does not handle threads or direct messages as these aren't supported by Discord webhooks.

2) Limited Functionality. The webhook adapter specifically focuses only on:
* Message Sending (creating new messages in channels)
* Message Editing (modifying previously sent messages)
* Message Deletion (removing messages sent through the webhook)
* History Fetching (retrieving message history on request)

3) Message edits and deletes only work for messages sent by the same webhook.

4) Simplified flow compared to the full Discord adapter.
* Initial Setup. Connects bots during startup and loads existing webhooks from Discord and configuration.
* Request Handling. Receives requests from the connectome framework, retrieves or creates webhooks as needed, sends received requests and returns Discord's identifiers for new messages.
* History Retrieval. Uses bot API to fetch message history when requested, no caching of message history.
