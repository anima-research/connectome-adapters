# Discord Adapter Documentation

### Purpose

The Discord Adapter enables integration between the connectome framework and Discord, allowing LLM-s to participate in Discord channels, respond to messages, and interact with users. This adapter facilitates:
* Receiving messages from Discord channels and DMs
* Sending messages to Discord conversations
* Processing reactions and other Discord-specific events
* Maintaining conversation context across Discord channels
* Managing file attachments between Discord and the LLM

### Discord.py Library

The adapter uses the official discord.py library to interact with the Discord API. This library handles authentication and security. For example, it uses:
* Bot Authentication. Applies Discord's bot token system for secure authentication.
* Privileged Gateway Intents. Requests specific permissions based on functionality needs.
* Rate Limit Handling. Built-in mechanisms to prevent API abuse and ensure compliance with Discord's policies.
* Secure WebSocket Connection. Establishes an encrypted connection to Discord's gateway.

### Discord connection

The adapter connects to Discord as a bot user.

### Discord client Implementation

The Discord client implementation connects to Discord's real-time gateway API and listens for events with the help of event handlers.
```python
    @self.bot.event
    async def on_ready():
        ...
    @self.bot.event
    async def on_message(message):
        ...
    @self.bot.event
    async def on_raw_message_edit(payload):
        ...
    @self.bot.event
    async def on_raw_message_delete(payload):
        ...
    @self.bot.event
    async def on_raw_reaction_add(payload):
        ...
    @self.bot.event
    async def on_raw_reaction_remove(payload):
        ...
```

### Configuration

The Discord adapter is configured through a YAML file with the following settings:
```yaml
adapter:
  adapter_type: "discord"                # Adapter type
  bot_token: "your_token"                # Discord bot authentication token
  application_id: "your_application_id"  # Discord application ID
  retry_delay: 5                         # Seconds to wait between connection attempts
  connection_check_interval: 300         # Seconds between connection health checks
  max_message_length: 1999               # Maximum message length (Discord limit: 2000)
  max_history_limit: 100                 # Maximum messages to fetch for history
  max_pagination_iterations: 10          # Maximum pagination iterations for history fetching

attachments:
  storage_dir: "adapters/discord_adapter/attachments"  # Local storage for attachments
  max_age_days: 30                                     # Maximum age of attachments before cleanup
  max_total_attachments: 1000                          # Maximum number of attachments to store at once
  cleanup_interval_hours: 24                           # How often to run attachment cleanup
  max_file_size_mb: 8                                  # Maximum single attachment size in MB
  max_attachments_per_message: 10                      # Maximum attachments allowed per message

caching:
  max_messages_per_conversation: 100  # Maximum messages to cache per conversation
  max_total_messages: 1000            # Maximum total messages in cache at once
  max_age_hours: 24                   # Maximum age of cached messages
  cache_maintenance_interval: 3600    # Seconds between cache cleanup runs
  cache_fetched_history: True         # Whether to cache messages that are fetched as history
logging:
  logging_level: "info"                                               # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_file_path: "adapters/discord_adapter/logs/development.log"      # Log file location
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"  # Log format
  max_log_size: 5242880                                               # Maximum log file size in bytes
  backup_count: 3                                                     # Number of log file backups to keep

rate_limit:
  global_rpm: 30                      # Requests per minute, it includes ALL requests to Discord
  per_conversation_rpm: 30            # Per-conversation rate limit
  message_rpm: 15                     # Message sending rate limit

socketio:
  host: "127.0.0.1"                   # Socket.IO server host on which the adapter is running
  port: 8082                          # Socket.IO server port on which the adapter is running
  cors_allowed_origins: "*"           # CORS allowed origins
```

### Discord specific features

1) Conversation Mapping. In the Discord adapter, conversations are identified and tracked using a composite ID formed from both the guild (server) ID and the channel ID: `guild_id/channel_id`. This format is used for channels and direct messages.
