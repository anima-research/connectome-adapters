# Zulip Adapter Documentation

### Purpose

The Zulip Adapter enables integration between the connectome framework and Zulip, allowing LLM-s to participate in Zulip streams and topics. This adapter facilitates:
* Receiving messages from Zulip streams and topics
* Sending messages to Zulip conversations
* Processing edited and deleted messages
* Handling reactions to messages
* Maintaining conversation context across Zulip streams
* Managing file attachments between Zulip and the LLM

### Zulip Client Library

The adapter uses the official Zulip Python library to interact with the Zulip API. This provides:
* REST API Implementation (complete interface to Zulip's API endpoints)
* Event System (event queue handling for receiving updates)
* Authentication (support for API key and OAuth authentication)
* Long Polling (efficient event retrieval with long polling)

The long polling is handled in a separate asyncio loop to avoid blocking the main thread.

### Zulip connection

The adapter can connect either as a bot or a user using zuliprc file.

The Zulip adapter implements a robust reconnection strategy that maintains system stability during network fluctuations or service interruptions. When a connection issue is detected, the adapter first cleanly disconnects from Zulip's API, then re-establishes both the API connection and event queue registration. This approach ensures message continuity even after queue expiration (which can occur after extended periods of inactivity). The adapter intelligently tracks consecutive reconnection attempts and implements configurable limits to prevent excessive API calls during prolonged outages, while automatically resetting the counter upon successful reconnection to ensure long-term reliability.

### Configuration

The Zulip adapter is configured through a YAML file with the following settings.

```yaml
adapter:
  adapter_type: "zulip"
  zuliprc_path: "adapters/zulip_adapter/zuliprc"  # Path to Zulip configuration file
  site: "https://example.com"                     # Zulip instance URL
  retry_delay: 5                                  # Seconds to wait between connection attempts
  connection_check_interval: 300                  # Seconds between connection health checks
  max_reconnect_attempts: 5                       # Max number of attempts to reconnect if connection lost
  max_message_length: 9000                        # Maximum message length
  chunk_size: 8192                                # Chunk size for processing large files
  max_history_limit: 800                          # Maximum messages to retrieve at once
  max_pagination_iterations: 5                    # Maximum pagination iterations for history
  emoji_mappings: "adapters/zulip_adapter/config/emoji_mappings.csv"  # Path to emoji mappings

attachments:
  storage_dir: "adapters/zulip_adapter/attachments"  # Local storage directory
  max_age_days: 30                                   # Maximum age of attachments before cleanup
  max_total_attachments: 1000                        # Maximum number of attachments to store
  cleanup_interval_hours: 24                         # How often to run attachment cleanup
  large_file_threshold_mb: 5                         # Threshold for large files in MB
  max_file_size_mb: 25                               # Maximum file size in MB

caching:
  max_messages_per_conversation: 100                 # Maximum messages to cache per conversation
  max_total_messages: 1000                           # Maximum total messages in cache
  max_age_hours: 24                                  # Maximum age of cached messages
  cache_maintenance_interval: 3600                   # Seconds between cache cleanup runs
  cache_fetched_history: True                        # Whether to cache fetched history messages

logging:
  logging_level: "info"                              # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_file_path: "adapters/zulip_adapter/logs/development.log"
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_log_size: 5242880                              # Maximum log file size in bytes
  backup_count: 3                                    # Number of log file backups to keep

rate_limit:
  global_rpm: 50                                     # Global rate limit (requests per minute)
                                                     # This applies to ALL requests to Zulip API
  per_conversation_rpm: 5                            # Per-conversation rate limit
  message_rpm: 5                                     # Message sending rate limit

socketio:
  host: "127.0.0.1"                                  # Socket.IO server host
  port: 8081                                         # Socket.IO server port
  cors_allowed_origins: "*"                          # CORS allowed origins
```

### Zulip-specific features

1) Conversation Mapping. In the Zulip adapter, conversations are identified using `stream_id/topic_name` for topic conversations in streams and the combination of all users IDs for private conversations (for example, `123_456`).

2) Topic Migrations. Zulip allows moving messages between topics, so the adapter tracks these topic migrations. When a message or group of messages is moved to a different topic, the adapter detects this change and emits relevant events. It handles three distinct scenarios when messages are moved between topics:
* Migration to a New Topic. When messages are moved to a previously non-existent topic, the adapter sends a `conversation_started` event for the new topic and fetches history for the new topic to establish context. It also emits `message_deleted` events for all moved messages in the original topic.
* Migration Between Existing Topics. When messages are moved between two topics that both already exist, the adapter emits `message_deleted` events for the moved messages in the source topic and `message_received` events for the moved messages in the destination topic. No conversation_started event is needed since both topics are known.
