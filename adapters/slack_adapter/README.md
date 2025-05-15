# Slack Adapter Documentation

### Purpose

The Slack Adapter enables integration between the connectome framework and Slack, allowing LLM-s to participate in Slack channels, respond to messages, and interact with users. This adapter facilitates:
* Receiving messages from Slack channels and direct messages
* Sending messages to Slack conversations
* Processing reactions and other Slack-specific events
* Maintaining conversation context across Slack workspaces and channels
* Managing file attachments between Slack and the LLM

### Slack SDK Integration

The adapter uses the official Slack SDK to interact with the Slack API. This provides:
* Socket Mode Connection. Establishes a WebSocket connection for real-time events
* Web Client API. Handles all Slack API calls for sending messages and interactions
* Authentication. Uses Slack's secure token-based authentication model
* Built-in Rate Limiting. Supports compliance with Slack's API rate limits

The adapter requires two types of tokens:
* Bot Token (xoxb- prefix). For API operations like sending messages
* App Token (xapp- prefix). For Socket Mode connection to receive events

### Slack connection

The adapter connects to Slack as a bot user.

The adapter employs a sophisticated reconnection mechanism specially designed for Socket Mode connections, which are used for real-time event delivery. When connectivity issues are detected, the adapter properly cleans up existing socket connections and tasks before establishing a new WebSocket connection, while preserving all object references to maintain system integrity. This implementation carefully manages asynchronous tasks with appropriate timeouts to prevent resource leaks, and includes proper state tracking to ensure the adapter can resume operations seamlessly after network interruptions. The reconnection logic is integrated with Slack's API authentication to verify both socket health and API access, providing comprehensive recovery capabilities for various failure scenarios.

### Configuration

The Slack adapter is configured through a YAML file with the following settings.

```yaml
adapter:
  adapter_type: "slack"
  bot_token: "xoxb-1234567890"        # Slack bot token (required)
  app_token: "xapp-1-1234567890"      # Slack app token for Socket Mode (required)
  retry_delay: 5                      # Seconds to wait between connection attempts
  connection_check_interval: 300      # Seconds between connection health checks
  max_reconnect_attempts: 5           # Max number of attempts to reconnect if connection lost
  max_message_length: 5000            # Maximum message length for Slack messages
  max_history_limit: 1000             # Maximum messages to fetch for history
  emoji_mappings: "adapters/slack_adapter/config/emoji_mappings.csv"  # Path to emoji mappings

attachments:
  storage_dir: "adapters/slack_adapter/attachments"  # Local storage directory
  max_age_days: 30                    # Maximum age of attachments before cleanup
  max_total_attachments: 1000         # Maximum number of attachments to store
  cleanup_interval_hours: 24          # How often to run attachment cleanup
  max_file_size_mb: 8                 # Maximum attachment size in MB
  max_attachments_per_message: 10     # Maximum attachments per message

caching:
  max_messages_per_conversation: 100  # Maximum messages to cache per conversation
  max_total_messages: 1000            # Maximum total messages in cache
  max_age_hours: 24                   # Maximum age of cached messages
  cache_maintenance_interval: 3600    # Seconds between cache cleanup runs
  cache_fetched_history: True         # Whether to cache fetched history messages

logging:
  logging_level: "info"               # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_file_path: "adapters/slack_adapter/logs/development.log"
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_log_size: 5242880               # Maximum log file size in bytes
  backup_count: 3                     # Number of log file backups to keep

rate_limit:
  global_rpm: 50                      # Global rate limit (requests per minute)
                                      # includes ALL requests to Slack API
  per_conversation_rpm: 10            # Per-conversation rate limit
  message_rpm: 5                      # Message sending rate limit

socketio:
  host: "127.0.0.1"                   # Socket.IO server host on which the adapter is running
  port: 8085                          # Socket.IO server port on which the adapter is running
  cors_allowed_origins: "*"           # CORS allowed origins
```

### Slack-specific features

1) Conversation Mapping. In the Slack adapter, conversations are identified using `team_id/channel_id` for channels, direct messages and multi-person direct messages.
2) Emoji Translation. Slack uses a different emoji format than most platforms. The adapter translates between Slack's string format and standard Unicode emojis that can be found in `emoji` library. Custom mapping file allows customization of emoji translations.
