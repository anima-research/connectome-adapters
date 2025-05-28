# Connectome Activity adapters

See [main repository](https://github.com/antra-tess/connectome) for more information.

### Project Overview
connectome-adapters is a framework that enables Large Language Models (LLMs) to interact with various messaging and communication platforms through a unified interface. This system allows LLMs to send and receive messages, process attachments, and maintain conversation context across multiple platforms.

### Purpose

The primary purpose of connectome-adapters is to:
* Provide Platform Abstraction. Create a standardized interface for communication platforms
* Handle Real-time Messaging. Process incoming and outgoing messages with proper context
* Manage Conversations. Track conversation state, history, and context
* Process Attachments. Handle media files and documents across platforms
* Ensure Reliability. Implement rate limiting, error handling, and recovery mechanisms

### Supported Adapters

Currently, the project supports the following communication platforms:
* Telegram: interact with Telegram chats, groups, and channels
* Discord: connect with Discord servers and channels
* Discord webhook: send messages to a Discord channel via a webhook
* Slack: communicate through Slack workspaces and channels
* Zulip: engage with Zulip streams and topics
* Text File: work with local filesystem for text file operations

### Setup

Each adapter instance handles exactly one user’s connection to a single provider (e.g., a user on Slack). The exception of rule is Discord webhook adapter. Also, each adapter runs in a separate process. One server can host many adapters, yet they require separate ports where they listen their platforms' events. To setup the adapter do the following steps.

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Copy the configuration file:
```bash
cp adapters/selected_adapter/config/selected_adapter_config.yaml.example selected_adapter_config.yaml
```

3. Update `selected_adapter_config.yaml` with your settings.

4. Run the application:
```bash
python adapters/selected_adapter/main.py
```

### Project Structure

The connectome-adapters codebase is organized into two main directories.

##### Core Directory

The core/ directory contains shared functionality that's reused across all adapters:

1) Socket.IO Client
* Manages communication between adapters and the connectome framework
* Handles event emission and reception
* Provides connection management and error handling

2) Rate Limiting
* Implements configurable rate limiting for all platform operations
* Prevents API quota violations
* Supports global, per-conversation, and per-operation limits

3) Caching
* Attachment Cache (short-term storage for media files)
* Message Cache (short-term storage for message history and context)

4) Base Conversation Management
* Base classes for tracking conversation state
* Methods for adding, updating, and deleting conversations
* Conversation context and history handling

5) Base Event Processing
* Base Incoming Event Processor standardizes platform events
* Base Outgoing Event Processor handles requests from the framework
* Event validation and transformation

6) Utilities...

##### Adapters Directory

The adapters/ directory contains platform-specific implementations:

1) Platform-Specific Clients
* Connection management for each platform
* Authentication handling
* Native API integration

2) Platform-Specific Event Processors
* Transform platform-specific events to standardized format
* Handle platform-specific message formats and features
* Process platform-specific attachment types

3) Platform-Specific Conversation Managers
* Track conversation entities unique to each platform
* Handle platform-specific conversation features (threads, channels, etc.)
* Maintain platform-specific user information

4) Platform-Specific Attachment Handlers
* Download and process platform-specific media formats
* Handle platform-specific attachment limits and requirements
* Implement platform-specific upload functionality

### Architecture

The connectome-adapters project follows a modular, event-driven architecture. The typical flow of an event through the system:

1) Platform to LLM:
* Platform Event → Platform Client → Incoming Event Processor → Socket.IO Client → connectome framework

2) LLM to Platform:
* connectome framework → Socket.IO Client → Outgoing Event Processor → Platform Client → Platform

##### Socket.IO Server
The Socket.IO server is a core component that manages real-time communication between the connectome-adapters and the connectome framework. It operates continuously to:
* Listen for incoming requests from the connectome framework
* Route platform events to the framework

The server runs as a persistent process that:
* Listens on a configurable host and port
* Maintains connections with connectome framework
* Handles event queueing and processing
* Ensures reliable message delivery

##### Outgoing Event Handling (LLM to Platform)

Currently, the server reacts to the following set of events.

```python
@self.sio.event
async def connect(sid, environ):
    """Event that indicates the connection of a new client"""
    ...

@self.sio.event
async def disconnect(sid):
    """Event that indicates the disconnection of an existing client"""
    ...

@self.sio.event
async def cancel_request(sid, data):
    """Event that should be emitted if it is necessary to cancel any queued bot_response event"""
    ...

@self.sio.event
async def bot_response(sid, data):
    """Event that should be emitted to perform any platform related action (send/edit message, etc.)"""
    ...
```

The Socket.IO server handles requests from the connectome framework the following way:
* Event Reception. The server receives a `bot_response` event with event type and data (see table below). Request is assigned a unique request_id for tracking.
* Queueing. Request is added to the event processing queue. Client receives a `request_queued` acknowledgment with the request_id.
* Processing. Request is passed to the appropriate adapter method. Adapter performs the requested operation on the platform.
* Response. On success, the client receives `request_success` with the request_id. On failure, the client receives `request_failed` with the request_id. For message sending, additional `message_ids` (platform-specific message identifiers) are included in the response. For history retrieval, additional `history` (platform-specific conversation history) is included in the response. Fot attachment fetching, additional `content` is included into response.
* Request Cancellation. Clients can cancel pending requests via the `cancel_request` event. Cancelled requests are removed from the queue if not yet processed.

The Socket.IO server handles the following event types from the connectome framework.

| Event Type      | Description                              | Required Data                                   |
|-----------------|------------------------------------------|-------------------------------------------------|
| send_message    | Send a new message to a conversation     | { <br>&nbsp;&nbsp;"event_type": "send_message", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"text": str,  <br>&nbsp;&nbsp;&nbsp;&nbsp;"mentions": List[str], <br>&nbsp;&nbsp;&nbsp;&nbsp;"attachments": List[<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"file_name": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"content": str <br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;} <br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;] <br>&nbsp;&nbsp;} <br>} |
| edit_message    | Edit an existing message                 | { <br>&nbsp;&nbsp;"event_type": "edit_message", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"text": str  <br>&nbsp;&nbsp;&nbsp;&nbsp;"mentions": List[str] <br>&nbsp;&nbsp;} <br>}|
| delete_message  | Delete a message                         | { <br>&nbsp;&nbsp;"event_type": "delete_message", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str <br>&nbsp;&nbsp;} <br>}|
| add_reaction    | Add a reaction to a message              | { <br>&nbsp;&nbsp;"event_type": "add_reaction", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"emoji": str <br>&nbsp;&nbsp;} <br>}|
| remove_reaction | Remove a reaction from a message         | { <br>&nbsp;&nbsp;"event_type": "remove_reaction", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"emoji": str <br>&nbsp;&nbsp;} <br>}|
| pin_message      | Pin message                              | { <br>&nbsp;&nbsp;"event_type": "pin_message", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str <br>&nbsp;&nbsp;} <br>}|
| unpin_message    | Unpin message                            | { <br>&nbsp;&nbsp;"event_type": "pin_message", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str <br>&nbsp;&nbsp;} <br>}|
| fetch_history   | Request conversation history (for more details on history fetching see "Important Flow Rules" section)             | { <br>&nbsp;&nbsp;"event_type": "fetch_history", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"limit": int, <br>&nbsp;&nbsp;&nbsp;&nbsp;"before": int <br>&nbsp;&nbsp;} <br>}|
| fetch_attachment | Request attachment                       | { <br>&nbsp;&nbsp;"event_type": "fetch_attachment", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"attachment_id": str <br>&nbsp;&nbsp;} <br>}|

##### Examples of outgoing event flow

1) Send message from the connectome framework to the adapter

The request that triggers the `bot_response` event for socket.io server.
```json
{
  "event_type": "send_message",
  "data": {
    "conversation_id": "C123",
    "text": "Hello World!",
    "mentions": ["user_id"],
    "attachments": []
  }
}
```

The first emitted event is `request_queued` with the request_id.
```json
{
  "adapter_type": "slack",
  "request_id": "R1"
}
```

After the request is processed in the adapter, the server emits either `request_failed`
```json
{
  "adapter_type": "slack",
  "request_id": "R1"
}
```

or `request_success`.
```json
{
  "adapter_type": "slack",
  "request_id": "R1",
  "data": {
    "message_ids": ["slack_id_989"]
  }
}
```

2) Cancel queued request

The request that triggers the `cancel_request` event for socket.io server.
```json
{
  "request_id": "R1"
}
```

After the request is processed in the adapter, the server emits either `request_failed`
```json
{
  "adapter_type": "slack",
  "request_id": "R1"
}
```

or `request_success`.
```json
{
  "adapter_type": "slack",
  "request_id": "R1"
}
```

##### Incoming Event Handling (Platform to LLM)

To ensure that the framework is able to receive platform's events it is necessary to add relevant listeners. At this moment the socket.io server emits the following set of events.

```python
@self.sio.event
async def connect(sid, data):
    """Event that indicates that the platform is connected to server through adapter"""
    ...

@self.sio.event
async def disconnect(sid, data):
    """Event that indicates that the platform is disconnected from server through adapter"""
    ...

@self.sio.event
async def bot_request(sid, data):
    """Event that is emitted in case one of platform events happened"""
    ...
```

Supported platform event types.


| Event Type           | Description                              | Included Data                                                          |
|----------------------|------------------------------------------|------------------------------------------------------------------------|
| conversation_started | New conversation initialized |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "conversation_started", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"history": List[Dict] <br>&nbsp;&nbsp;} <br>}|
| message_received | New message from the platform | { <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_received", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"adapter_name": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"sender": { "user_id": str, "display_name": str }, <br>&nbsp;&nbsp;&nbsp;&nbsp;"text": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"thread_id": Optional[str], <br>&nbsp;&nbsp;&nbsp;&nbsp;"attachments": List[Dict],  <br>&nbsp;&nbsp;&nbsp;&nbsp;"is_direct_message": bool, <br>&nbsp;&nbsp;&nbsp;&nbsp;"timestamp": int <br>&nbsp;&nbsp;} <br>} |
| message_updated      | Message was edited                       |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_updated", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"new_text": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| message_deleted      | Message was deleted                      |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_deleted", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| reaction_added       | Reaction added to message                |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "reaction_added", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"emoji": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| reaction_removed     | Reaction removed from message            |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "reaction_removed", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"emoji": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| message_pinned       | Message pinned                           |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_pinned", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| message_unpinned | Message unpinned |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_unpinned", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|

##### Examples of incoming event flow

1) The beginning of a new conversation

The adapter emits `conversation_started` event when a new conversation is detected.
```json
{
  "adapter_type": "slack",
  "event_type": "conversation_started",
  "data": {
    "conversation_id": "C123",
    "history": [
      {
        "adapter_name": "slack_bot_arthur",
        "message_id": "message_id_989",
        "conversation_id": "guild_id_123/channel_id_456",
        "text": "Hello World!",
        "sender": {
          "user_id": "U123",
          "display_name": "Alice"
        },
        "thread_id": "root_message_id_101",
        "is_direct_message": False,
        "attachments": [
          {
            "attachment_id": "unique_attachment_id",
            "attachment_type": "document",
            "file_extension": "txt",
            "size": 12345,
            "processable": True,
            "content": None
          }
        ],
        "timestamp": 1620000000000
      }
    ]
  }
}
```

After that, the adapter emits `message_received` event for a new message that started the conversation for the conversation manager.
```json
{
  "adapter_type": "slack",
  "event_type": "message_received",
  "data": {
    "adapter_name": "slack_bot_arthur",
    "message_id": "message_id_990",
    "conversation_id": "guild_id_123/channel_id_456",
    "text": "Hello, hello!",
    "sender": {
      "user_id": "U125",
      "display_name": "Bob"
    },
    "thread_id": "message_id_989",
    "is_direct_message": False,
    "attachments": [
      {
        "attachment_id": "unique_attachment_id",
        "attachment_type": "document",
        "file_extension": "txt",
        "size": 12345,
        "processable": True,
        "content": "dGVzdAo="
      }
    ],
    "timestamp": 1620000000000
  }
}
```

##### Attachment handling
The connectome-adapters framework provides a comprehensive system for processing attachments in both incoming (platform to LLM) and outgoing (LLM to platform) directions across different messaging platforms.

1) Incoming Attachment Processing (Platform to LLM)

* Message Reception. When a platform message contains attachments, the adapter identifies all attachments and extracts their metadata regardless of size. All attachments are included in the message metadata for awareness.
* Automatic Download. The adapter automatically downloads all attachments that are under the configured `max_file_size_mb` limit. Attachments exceeding the size limit are marked with `processable` set to False and only metadata is retained. Downloaded attachments are stored in the attachment cache.
* Size Limitations. The `max_file_size_mb` configuration is critical as it determines what can be processed. This limit should be set with multiple constraints in mind: a) Socket.IO transmission capacity (all attachments are sent together, underlying protocol allows up to 16MB during one transmission), b) LLM processing capabilities (what is the max size of a single attachment that can be handled by LLM in question).
* History Fetching. When conversation history is fetched, all valid attachments (under size limit) are downloaded. Only attachment metadata is included in message history information. File content is not included in history responses to minimize payload size, therefore, `conetnt` is always None. Later, the necessary atatchment content can be fetched with the help of `fetch_attachment` request.

2) Outgoing Attachment Processing (LLM to Platform)

* Sending Attachments. The framework can include attachments with outgoing messages. The adapter processes file content and uploads it to the platform.
* Fetch Attachment. The framework can explicitly request attachment content via `fetch_attachment`. The adapter accepts an attachment ID from the framework and checks if the attachment exists in the cache. If found, the cached attachment content is returned. If there is no cached attachment, then there request will fail.

3) Encoding and Format

For Slack, Telegram, Zulip, and Discord platforms attachment content is standardized with the help of base64 encoding. All file content is encoded as base64 strings when transmitted through the Socket.IO interface. When sending attachments to platforms, provide the file content as a base64-encoded string. When receiving attachments from platforms, file content (if included) will be provided as a base64-encoded string.

Downloader code.
```python
with open(local_file_path, "rb") as f:
    file_content = base64.b64encode(f.read()).decode("utf-8")
```

Uploader code (before we load content to the file and send that file to the platform).
```python
file_content = base64.b64decode(attachment.content)
```

##### Data Handling and Caching
connectome-adapters is designed with a strong focus on data minimization and ephemeral processing. Two key systems handle temporary data storage:

1) Message Caching System. The message cache is designed for temporary storage of conversation context. Messages are stored only in memory, not persisted to disk. There is no permanent storage of message content. Message data is used only for context maintenance and history retrieval. It has automatic cleanup that runs at configurable intervals. Messages older than the configured time-to-live (TTL) are automatically removed. Default TTL is typically set to 24 hours but can be configured based on requirements. The message cache also follows the principle of minimal data retention. It only stores information needed for conversation tracking. It maintains just enough context for the connectome to engage effectively. Configuration options to limit the number of messages stored per conversation are also available.

2) Attachment Cache. The attachment cache is designed for temporary storage of media files. Files are downloaded and stored in a temporary directory. The cache is used to avoid downloading the same file multiple times. When an adapter starts, it checks the configured `storage_dir` location. Any existing attachments in this directory are automatically added to the cache. This allows persistence across adapter restarts. A background task periodically runs to clean the attachment cache. Two main cleanup criteria are enforced: `max_age_days` (attachments older than this are removed) and `max_total_attachments` (if exceeded, oldest attachments are removed first). This ensures the cache doesn't grow unbounded; also, due to this the attachment cache follows the principle of minimal data retention. IMPORTANT! For security purposes, attachments must be manually deleted when an adapter is permanently decommissioned.

##### Important Flow Rules
1) Conversation Initialization Requirement. The adapter must have received at least one message from a conversation before it will send to that conversation. This ensures the bot only responds in channels where it's added and where there is new messages activity.
2) Even if a valid conversation ID is provided, the adapter will reject requests to "unknown" conversations.
3) History First Principle. When a new conversation is detected, history is always sent before the triggering message. This provides the LLM with conversation context before it needs to respond.
4) Event Tracking Scope. The adapter emits edit/delete/reaction/pin/unpin events for messages that are actively tracked in the conversation manager. These events are only tracked for messages in the current context window. Changes to messages outside the tracked history (very old messages) are not monitored or reported. This design choice balances comprehensive tracking with efficient resource usage.
5) History Transience. If history is fetched but not stored in the adapter's cache, subsequent modifications to those messages will not generate events. The adapter prioritizes tracking recent and active conversations rather than maintaining a complete historical record.
6) On-Demand History Retrieval. The adapter supports explicit history fetching via requests from the framework. This allows the connectome framework to obtain more context when needed for a conversation. Requests require either `after` or `before` parameter. Parameters must be timestamps in milliseconds (Unix epoch).
7) Caching Strategy. The adapter first attempts to serve history requests from its cache. If the requested messages aren't in cache, the adapter will fetch them from platforms. This approach minimizes API usage while maintaining responsive performance.
8) Cache Utilization. Fetched history is cached according to the `cache_fetched_history` configuration setting. When enabled, this improves performance for repeated history requests and reduces API load. Cache entries respect the configured TTL (time-to-live) settings to manage memory usage.
9) Attachments handling. All attachment content is transmitted through Socket.IO to LLMs. This creates a practical limit on attachment size. When multiple attachments are in a single message, their combined size must be considered. Additionally, the attachment cache contains potentially sensitive information, therefore, manual cleanup is required when decommissioning an adapter permanently. Regular automated cleaning helps minimize data exposure risk.
10) Message length. When the connectome framework sends a new message, the adapter checks the legth of message and, if necessary, splits it into chunks according to the message length limit imposed by a corresponding platform (the limit is configurable; to set it it is necessary to update `max_message_length` in the config file). Consequently, one large connectome framework message may result in 2 or more platform messages. The platform message IDs will be returned to the framework, yet that may represent a problem for future message editing or deleting. Therefore, it is strongly recommended to portion messages before sending them to the adapter. Additionally, when the connectome framework edits an existing message, it should provide the new text in accordance with message length limits, otherwise, it will result in an error.
11) Mentions. It is possible to mention users or the whole set of conversation members during sending or editing messages. To mention ereyone it is necessary to submit `all` in the `mentions` array. To mention a certain user it is necessary to submit that user ID in the `mentions` array. Keep in mind, that the connectome adapter receives user ID either through history fetching, or processing new platform messages. These values should be used for mentioning.
12) Notification Filtering Policy. Adapters track all messages internally, but only notify models about message events (creation/editing/deletion) when they are initiated by external users. Events triggered by the connectome framework itself are not reported back to the model to prevent redundant information and notification loops. While this filtering reduces noise, it means the model won't be notified if an administrator deletes one of the framework's messages. This design prioritizes clean conversation flow over complete event tracking.
13) Admin Actions (Pin/Unpin). The connectome-adapters support pinning and unpinning messages on Slack, Discord (excluding webhook connections), and Telegram platforms. These actions typically require the bot to have appropriate permissions configured on the platform (e.g., "Manage Messages" in Discord, "pins:write" scope in Slack). The framework does not support pinning in Zulip, which uses a different organizational model based on topics.

### Configuration
The configuration is stored in YAML format. What can be configured is listed in README.md-s of relevant adapters.

### Privacy Considerations
* Message Content: Processed ephemerally and not stored permanently
* User Information: Minimal tracking of user identifiers for conversation context
* Conversation History: Configurable retention policies

### Scalability Model
The connectome-adapters employ a process-per-user architecture to ensure reliability and throughput scalability. Each adapter instance handles exactly one user's connection to a single platform (e.g., one Slack user, one Zulip bot, etc.) and runs in its own isolated process, listening on a dedicated port. This design intentionally separates concerns, allowing for independent scaling, targeted resource allocation, and fault isolation between adapter instances.

For high-volume deployments, horizontal scaling is achieved by deploying multiple adapters with different user credentials, each handling a subset of conversations. While each adapter operates independently, they all communicate with the same central framework through the standardized Socket.IO interface, creating a unified experience at the application level. This architecture naturally supports load distribution across multiple machines and provides resilience against individual adapter failures.

Discord webhook adapter is the exception to the one-user-per-adapter rule, as it can send/edit/delete messages through bots' webhook endpoints. This adapter can also be scaled because the configuration of bots is defined manually and bots can be split between different instances of webhook adapter running on different ports.

Text file adapter is designed to work with a single operating system where it runs, yet it is possible to have more then one text file adapter running in the same OS.

This architecture strikes a balance between the simplicity of having a single adapter per platform type and the scalability needs of enterprise deployments, allowing teams to start with a minimal deployment and scale out incrementally as their usage grows.

### Future work
* Filesystem
* WikiGraph
* MCP Host
