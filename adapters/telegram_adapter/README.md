# Telegram Adapter Documentation

### Purpose

The Telegram Adapter enables integration between the connectome framework and Telegram, allowing LLM-s to participate in Telegram chats, groups, and channels. This adapter facilitates:
* Receiving messages from Telegram chats, groups, and channels
* Sending messages to Telegram conversations
* Processing edited and deleted messages
* Monitoring chat actions (pin, unpin)
* Maintaining conversation context across Telegram chats
* Managing file attachments between Telegram and the LLM

### Telethon Library

The adapter uses the Telethon library to interact with the Telegram API. This provides:

* API Layer Implementation. Complete implementation of Telegram's MTProto protocol
* Event System. Comprehensive event handling for all Telegram activities
* Authentication. Support for both bot and user authentication methods
* Media Handling. Robust file upload and download capabilities

### Telegram connection

The adapter can connect either as a bot or a user. While the first option is recommended, the second one provides more options to interact with the Telegram content via tracking deleted messages, adding/removing reactions and fetching history.

There is no automatic reconnection mechanism for Telegram; if anything fails, it should be restarted manually.

### Client Implementation

The Telegram client implementation leverages Telethon's event system to process incoming messages and other events. For that the set of event handlers is implemented.
```python
def _setup_event_handlers(self) -> None:
    ...
    @self.client.on(events.NewMessage())
    async def on_new_message(event):
        ...
    @self.client.on(events.MessageEdited()) # also, handles message reactions
    async def on_edited_message(event):
        ...
    @self.client.on(events.MessageDeleted())
    async def on_deleted_message(event):
        ...
    @self.client.on(events.ChatAction())  # handles pin/unpin events
    async def on_chat_action(event):
        ...
```

### Configuration

The Telegram adapter is configured through a YAML file with the following settings.

```yaml
adapter:
  adapter_type: "telegram"
  api_id: "XXXXXXX"                 # Your Telegram API ID (required)
  api_hash: "XXXXXXXXXX"            # Your Telegram API hash (required)
  bot_token: "XXXXXXXX"             # Your bot token (optional if phone provided)
  phone: "XXXXXXXX"                 # Your phone number (optional if bot_token provided)
  retry_delay: 5                    # Seconds to wait between connection attempts
  connection_check_interval: 300    # Seconds between connection health checks
  max_reconnect_attempts: 5         # Max number of attempts to reconnect if connection lost
  flood_sleep_threshold: 120        # Seconds to sleep on flood wait
  max_message_length: 4000          # Maximum message length
  max_history_limit: 100            # Maximum messages to retrieve at once
  max_pagination_iterations: 10     # Maximum pagination iterations for history

attachments:
  storage_dir: "adapters/telegram_adapter/attachments"  # Local storage directory
  max_age_days: 30                     # Maximum age of attachments before cleanup
  max_total_attachments: 1000          # Maximum number of attachments to store
  cleanup_interval_hours: 24           # How often to run attachment cleanup
  large_file_threshold_mb: 5           # Threshold for large files in MB
  max_file_size_mb: 50                 # Maximum file size in MB

caching:
  max_messages_per_conversation: 100  # Maximum messages to cache per conversation
  max_total_messages: 1000            # Maximum total messages in cache
  max_age_hours: 24                   # Maximum age of cached messages
  cache_maintenance_interval: 3600    # Seconds between cache cleanup runs
  cache_fetched_history: True         # Whether to cache fetched history messages

logging:
  logging_level: "info"             # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_file_path: "adapters/telegram_adapter/logs/development.log"
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_log_size: 5242880             # Maximum log file size in bytes
  backup_count: 3                   # Number of log file backups to keep

rate_limit:
  global_rpm: 30                    # Global rate limit (requests per minute)
                                    # This applies to ALL requests to Telegram API
  per_conversation_rpm: 30          # Per-conversation rate limit
  message_rpm: 15                   # Message sending rate limit

socketio:
  host: "127.0.0.1"                 # Socket.IO server host
  port: 8080                        # Socket.IO server port
  cors_allowed_origins: "*"         # CORS allowed origins
```

### Telegram-specific features

1) Conversation Mapping. In the Telegram adapter, conversations are identified by:
* For private chats: the peer ID (user ID)
* For groups: the negative group ID
* For channels: the negative channel ID with a -100 prefix
* For supergroups: the negative supergroup ID with a -100 prefix

2) Conversation Migrations. Telegram sometimes migrates groups to supergroups. The adapter does not track these migrations, however, it handles them anyway. Once the migration happens and the conversation continues, the adapter receives the first new message and retrieves the history that is sent to the connectome framework. After that, the old conversation will be removed from the adapter's cache as a result of standard cleanup process, while the new one will be maintained as usual.

3) Telegram's File Expiration Policy. Attachments from older messages (typically more than a few days old) may no longer be downloadable, even though the messages themselves are still visible in history.
