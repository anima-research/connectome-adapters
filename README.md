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

### Project Structure

The connectome-adapters codebase is organized into two main directories:

#### Core Directory
The core/ directory contains shared functionality that's reused across all adapters:

1) Socket.IO Client:
* Manages communication between adapters and the connectome framework
* Handles event emission and reception
* Provides connection management and error handling

2) Rate Limiting:
* Implements configurable rate limiting for all platform operations
* Prevents API quota violations
* Supports global, per-conversation, and per-operation limits

3) Caching:
* Attachment Cache: Temporary storage for media files
* Message Cache: Short-term storage for message history and context

4) Base Conversation Management:
* Base classes for tracking conversation state
* Methods for adding, updating, and deleting conversations
* Conversation context and history handling

5) Base Event Processing:
* Base Incoming Event Processor: Standardizes platform events
* Base Outgoing Event Processor: Handles requests from the framework
* Event validation and transformation

6) Utilities...

#### Adapters Directory
The adapters/ directory contains platform-specific implementations:

1) Platform-Specific Clients:
* Connection management for each platform
* Authentication handling
* Native API integration

2) Platform-Specific Event Processors:
* Transform platform-specific events to standard format
* Handle platform-specific message formats and features
* Process platform-specific attachment types

3) Platform-Specific Conversation Managers:
* Track conversation entities unique to each platform
* Handle platform-specific conversation features (threads, channels, etc.)
* Maintain platform-specific user information

4) Platform-Specific Attachment Handlers:
* Download and process platform-specific media formats
* Handle platform-specific attachment limits and requirements
* Implement platform-specific upload functionality

### Architecture

The connectome-adapters project follows a modular, event-driven architecture. Each adapter instance handles exactly one user’s connection to a single provider (e.g., a user on Slack). The exception of rule is Discord webhook adapter. Also, each adapter runs in a separate process. One server can host many adapters, yet they require separate ports where they listen their platforms' events.

#### Communication Flow
The typical flow of a message through the system:

1) Platform to LLM:
* Platform Event → Platform Client → Incoming Event Processor → Socket.IO Client → connectome framework

2) LLM to Platform:
* connectome framework → Socket.IO Client → Outgoing Event Processor → Platform Client → Platform

#### Socket.IO Server and Event Handling
The Socket.IO server is a core component that manages real-time communication between the connectome-adapters and the connectome framework. It operates continuously to:
* Listen for incoming requests from the connectome framework
* Route platform events to the framework

The server runs as a persistent process that:
* Listens on a configurable host and port
* Maintains connections with connectome framework clients
* Handles event queueing and processing
* Ensures reliable message delivery

The Socket.IO server handles requests from the connectome framework the following way:
* Event Reception. The server receives a `bot_response` event with event type and data. Request is assigned a unique request_id for tracking.
* Queueing. Request is added to the event processing queue. Client receives a `request_queued` acknowledgment with the request_id.
* Processing. Request is passed to the appropriate adapter method. Adapter performs the requested operation on the platform.
* Response. On success, the client receives `request_success` with the request_id. On failure, the client receives `request_failed` with the request_id and error details. For message sending, additional `message_ids` (platform-specific message identifiers) are included in the response. For history retrieval, additional `history` (platform-specific conversation history) is included in the response.
* Request Cancellation. Clients can cancel pending requests via the `cancel_request` event. Cancelled requests are removed from the queue if not yet processed.

The Socket.IO server handles the following request types from the connectome framework.

| Event Type      | Description                              | Required Data                                   |
|-----------------|------------------------------------------|-------------------------------------------------|
| send_message    | Send a new message to a conversation     | { <br>&nbsp;&nbsp;"event_type": "send_message", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"text": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"attachments": List[Dict] <br>&nbsp;&nbsp;} <br>} |
| edit_message    | Edit an existing message                 | { <br>&nbsp;&nbsp;"event_type": "edit_message", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"text": str <br>&nbsp;&nbsp;} <br>}|
| delete_message  | Delete a message                         | { <br>&nbsp;&nbsp;"event_type": "delete_message", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str <br>&nbsp;&nbsp;} <br>}|
| add_reaction    | Add a reaction to a message              | { <br>&nbsp;&nbsp;"event_type": "add_reaction", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"emoji": str <br>&nbsp;&nbsp;} <br>}|
| remove_reaction | Remove a reaction from a message         | { <br>&nbsp;&nbsp;"event_type": "remove_reaction", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"emoji": str <br>&nbsp;&nbsp;} <br>}|
| fetch_history   | Request conversation history (for more details on history fetching see "Important Flow Rules" section)             | { <br>&nbsp;&nbsp;"event_type": "fetch_history", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"limit": int, <br>&nbsp;&nbsp;&nbsp;&nbsp;"before": int <br>&nbsp;&nbsp;} <br>}|

Meanwhile, adapters send the following events to the LLM framework using `bot_request` event.

| Event Type           | Description                              | Included Data                                                          |
|----------------------|------------------------------------------|------------------------------------------------------------------------|
| connect              | Adapter connection status                | { "adapter_type": str }                                                |
| disconnect           | Adapter disconnection notification       | { "adapter_type": str }                                                |
| conversation_started | New conversation initialized |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "conversation_started", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"history": List[Dict] <br>&nbsp;&nbsp;} <br>}|
| message_received | New message from the platform | { <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_received", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"adapter_name": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"sender": { "user_id": str, "display_name": str }, <br>&nbsp;&nbsp;&nbsp;&nbsp;"text": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"thread_id": Optional[str], <br>&nbsp;&nbsp;&nbsp;&nbsp;"attachments": List[Dict], <br>&nbsp;&nbsp;&nbsp;&nbsp;"timestamp": int <br>&nbsp;&nbsp;} <br>} |
| message_updated      | Message was edited                       |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_updated", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"new_text": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| message_deleted      | Message was deleted                      |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_deleted", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| reaction_added       | Reaction added to message                |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "reaction_added", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"emoji": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| reaction_removed     | Reaction removed from message            |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "reaction_removed", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"emoji": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| message_pinned       | Message pinned                           |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_pinned", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|
| message_unpinned | Message unpinned |{ <br>&nbsp;&nbsp;"adapter_type": str, <br>&nbsp;&nbsp;"event_type": "message_unpinned", <br>&nbsp;&nbsp;"data": { <br>&nbsp;&nbsp;&nbsp;&nbsp;"message_id": str, <br>&nbsp;&nbsp;&nbsp;&nbsp;"conversation_id": str <br>&nbsp;&nbsp;} <br>}|

#### Data Handling and Caching
connectome-adapters is designed with a strong focus on data minimization and ephemeral processing. Two key systems handle temporary data storage:

1) Message Caching System. The message cache is designed for temporary storage of conversation context. Messages are stored only in memory, not persisted to disk. There is no permanent storage of message content. Message data is used only for context maintenance and history retrieval. It has automatic cleanup that runs at configurable intervals. Messages older than the configured time-to-live (TTL) are automatically removed. Default TTL is typically set to 24 hours but can be configured based on requirements. The message cache also follows the principle of minimal data retention. It only stores information needed for conversation tracking. It maintains just enough context for the connectome to engage effectively. Configuration options to limit the number of messages stored per conversation are also available.

2) Attachment Cache. The attachment cache is designed for temporary storage of media files. Files are downloaded and stored in a temporary directory. The cache is used to avoid downloading the same file multiple times. Files are deleted after a configurable TTL. There is also automatic cleanup, and the attachment cache follows the principle of minimal data retention.

#### Important Flow Rules
1) Conversation Initialization Requirement. The adapter must have received at least one message from a conversation before it will send to that conversation. This ensures the bot only responds in channels where it's added and where there is new messages activity.
2) Even if a valid conversation ID is provided, the adapter will reject requests to "unknown" conversations.
3) History First Principle. When a new conversation is detected, history is always sent before the triggering message. This provides the LLM with conversation context before it needs to respond.
4) Event Tracking Scope. The adapter emits edit/delete/reaction/pin/unpin events for messages that are actively tracked in the conversation manager. These events are only tracked for messages in the current context window. Changes to messages outside the tracked history (very old messages) are not monitored or reported. This design choice balances comprehensive tracking with efficient resource usage.
5) History Transience. If history is fetched but not stored in the adapter's cache, subsequent modifications to those messages will not generate events. The adapter prioritizes tracking recent and active conversations rather than maintaining a complete historical record.
6) On-Demand History Retrieval. The adapter supports explicit history fetching via requests from the framework. This allows the connectome framework to obtain more context when needed for a conversation. Requests require either `after` or `before` parameter. Parameters must be timestamps in milliseconds (Unix epoch).
6) Caching Strategy. The adapter first attempts to serve history requests from its cache. If the requested messages aren't in cache, the adapter will fetch them from platforms. This approach minimizes API usage while maintaining responsive performance.
7) Cache Utilization. Fetched history is cached according to the `cache_fetched_history` configuration setting. When enabled, this improves performance for repeated history requests and reduces API load. Cache entries respect the configured TTL (time-to-live) settings to manage memory usage.

#### Examples of flows

##### Send Message from the connectome framework to the adapter
Request that triggers the `bot_response` event for socket.io server.
```json
{
  "event_type": "send_message",
  "data": {
    "conversation_id": "C123",
    "text": "Hello World!",
    "attachments": []
  }
}
```
First emitted event is `request_queued` with the request_id.
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
  "message_ids": ["slack_id_989"]
}
```

##### Cancel queued request
Request that triggers the `cancel_request` event for socket.io server.
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

##### The beginning of a new conversation
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
        "attachments": [],
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
    "attachments": [],
    "timestamp": 1620000000000
  }
}
```

### Configuration
The configuration is stored in YAML format. What can be configured is listed in README.md-s of relevant adapters.

### Privacy Considerations
* Message Content: Processed ephemerally and not stored permanently
* User Information: Minimal tracking of user identifiers for conversation context
* Conversation History: Configurable retention policies

### Setup
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

#### Future work
* Filesystem
* WikiGraph
* MCP Host
* MCP Host
