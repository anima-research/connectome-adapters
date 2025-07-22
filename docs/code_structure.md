# Connectome Activity adapters
This section is primarily about platforms' adapters (Discord, Slack, Telegram and Zulip). The code of other adapters is explained in relevant README-s.

The connectome-adapters codebase is organized into two main directories. The src/core/ directory contains shared functionality that's reused across all adapters. The src/adapters/ directory contains platform-specific implementations.

### Core

#### Configuration
Each platform adapter's behavior is governed by settings defined in a dedicated configuration file located at `config/<adapter-type>_config.yaml`. When an adapter initializes, this file is parsed and its settings are stored in an instance of the `Config` class (defined in `src/core/utils/config.py`). Configuration settings are organized into logical categories (for example, "adapter", "caching", "logging") making them easier to manage and access. To retrieve a setting in your code, use the `get_setting` method with the category name and setting name as arguments.
```python
config.get_setting("adapter", "new_setting")
```
If you need to add a new setting to an existing category, simply add it to the appropriate section in the configuration file. However, if you need to create an entirely new category, you must modify the Config class to ensure it recognizes and properly parses the new category during initialization.

#### Rate Limiting
The `RateLimiter` class (defined in `src/core/rate_limiter/rate_limiter.py`) is a singleton class that prevents adapters from overwhelming platform APIs with too many requests. This service can be called from anywhere in the adapter code using the `limit_request` method, which calculates appropriate waiting times before new requests are sent. The rate limits are calculated on the basis of three key metrics:
* `global_rpm`. The total number of all requests (including operations like `get_user`, `add_reaction`, etc.) sent from the adapter per minute
* `per_conversation_rpm`. The number of requests sent within a single conversation per minute
* `message_rpm`. The number of messages sent from the adapter per minute

#### Caching System
The `Cache` singleton (defined in `src/core/cache/cache.py`) serves as a central access point for three specialized cache types: `MessageCache`, `AttachmentCache`, and `UserCache`.

#### Message Caching
The `MessageCache` (defined in `src/core/cache/message_cache.py`) stores conversation messages in a nested dictionary structure where messages can be accessed via conversation IDs and message IDs. The cache tracks the total number of stored messages and provides methods like `get_message_by_id`, `get_messages_by_conversation_id`, `add_message`, and `delete_message` for managing cached content. It also supports message migration between conversations through the `migrate_message` method.

When initializing `MessageCache`, you can enable automatic maintenance by setting the `start_maintenance` parameter to true. This creates an asynchronous background task that periodically checks if cache cleaning is necessary. The maintenance interval is configurable through the `cache_maintenance_interval` setting in the "caching" category. Cache cleaning is triggered when either the number of messages in a conversation exceeds `max_messages_per_conversation` or when the total message count surpasses `max_total_messages`.

#### Attachment Caching
The `AttachmentCache` (defined in `src/core/cache/attachment_cache.py`) manages file attachments through a dictionary mapping attachment IDs to `CachedAttachment` objects. Similar to the message cache, it provides methods for retrieving, adding, and deleting attachments.

When downloading a new attachment, the cache stores it in a configurable directory specified by the `storage_dir` setting in the "attachments" category. The storage structure is organized first by attachment type (document, image, etc.), then by attachment ID. For example, if the storage directory is set to `/our_downloads` and an image with ID `unique_image_id_123` is downloaded, the resulting structure would be.
```bash
our_downloads/
our_downloads/image/
our_downloads/image/unique_image_id_123/
our_downloads/image/unique_image_id_123/unique_image_id_123.jpg
our_downloads/image/unique_image_id_123/unique_image_id_123.json
```
Attachments are preserved on disk because re-downloading them would be resource-intensive. When the adapter restarts, the attachment cache repopulates itself by reading metadata from JSON files using the private `_upload_existing_attachments` method.

The attachment cache also supports maintenance through the `start_maintenance` parameter, which launches a background task that runs every `cleanup_interval_hours` (configurable in the "attachments" category). Cleaning occurs when either the total attachment count exceeds `max_total_attachments` or when attachments age beyond `max_age_days`.

#### User Caching
The `UserCache` (defined in `src/core/cache/user_cache.py`) stores information about platform users in a dictionary mapping user IDs to `UserInfo` objects. Like other caches, it provides methods for retrieving, adding, and removing users through `get_user_by_id`, `add_user`, and `delete_user` methods.

#### Emoji Conversion
The `EmojiConverter` (defined in `src/core/utils/emoji_converter.py`) service standardizes emoji handling across platforms. Different platforms represent reactions in varying formats - Zulip might use emoji names like "red_heart" while Discord uses actual emoji characters. To provide a consistent experience, the adapter architecture converts all emoji to standard names before sending them to the LLM. For platforms like Zulip and Slack, the converter uses a CSV mapping file that translates platform-specific emoji names to the corresponding Python emoji library names. This mapping file only needs to include emoji names that differ from the standard Python emoji library format. By standardizing emoji across all platforms, the adapter ensures consistent representation regardless of the originating platform, simplifying emoji handling for LLMs.

### Adapters

#### Main Entry Point
The primary entry point for any adapter is located at `src/adapters/your_adapter/main.py`. When executed, this script performs three crucial initialization steps:
1. Initializes the necessary singleton classes for the adapter
2. Creates an instance of the `SocketIOServer` class that facilitates communication between the adapter and Connectome with its LLMs
3. Instantiates the platform-specific `Adapter` class that orchestrates all adapter components

#### Adapter
The `Adapter` class is defined as an abstract base class in `src/core/adapter/adapter.py`. However, each platform adapter implements its own version in `src/adapters/your_adapter/adapter.py` to accommodate platform-specific behaviors and requirements.

The fundamental responsibilities of the `Adapter` class include:
1. Establishing a connection to the platform via the platform-specific `Client` class
2. Retrieving account information for the bot identity on the platform
3. Setting up event processors:
* `IncomingEventProcessor` handles events originating from the platform
* `OutgoingEventProcessor` manages events initiated by Connectome that need to be sent to the platform
4. Listening for both types of events and routing them to the appropriate processors

This event routing is accomplished through two key methods.
```python
async def process_incoming_event(self, event: Any) -> None:
    # ...
    for event_info in await self.incoming_events_processor.process_event(event):
        await self.socketio_server.emit_event("bot_request", event_info)

async def process_outgoing_event(self, data: Any) -> Dict[str, Any]:
    # ...
    result = await self.outgoing_events_processor.process_event(data)
    # ...
    return result
```

The `Adapter` class actively monitors its connection to the platform through an asynchronous background process defined in the `_monitor_connection` method. This process periodically checks if the established connection remains active. If the connection is lost, the adapter attempts to automatically reconnect. After exhausting all reconnection attempts, it raises a `RuntimeError` with the message "Connection check failed." When the connection is healthy - either maintained from the original connection or successfully reestablished - the adapter periodically emits a `connect` event to inform Connectome of its operational status.

The reconnection mechanism varies significantly between platforms.
Slack: the adapter explicitly attempts reconnection with `await self.client.reconnect()`.
Discord: no explicit reconnection logic is implemented as the official `discord.py` library handles reconnection automatically.
Telegram: explicit reconnection is avoided to prevent Flood errors and excessive timeouts, requiring more careful manual handling.

The Adapter class also handles error conditions by emitting `disconnect` events when the connection fails or when the adapter is intentionally shutting down.

#### Platform-Specific Client Implementation
Each platform requires its own `Client` implementation (found in `src/adapters/your_adapter/client.py`). While all clients share common methods like `connect()` and `disconnect()` for establishing and terminating platform sessions, the implementation details vary substantially between platforms.

The `Client` class is also responsible for configuring event listeners that trigger when platform events relevant to Connectome and the LLM occur. These event handling mechanisms are highly platform-dependent.

Example of Discord event handling.
```python
def _setup_event_handlers(self) -> None:
    # ...
    @self.bot.event
    async def on_message(message):
        await self.process_event({"type": "new_message", "event": message})
    # ...
```

Example of Slack event handling.
```python
async def connect(self) -> bool:
    # ...
    self.socket_client = SocketModeClient(app_token=app_token, web_client=self.web_client)
    self.socket_client.socket_mode_request_listeners.append(self._handle_slack_event)
    # ...

async def _handle_slack_event(self, _: Any, request: Any) -> None:
    # ...
    response = SocketModeResponse(envelope_id=request.envelope_id)
    event = request.payload.get("event", {})
    event_type = event.get("type", None)
    event_subtype = event.get("subtype", None)
    await self.process_event({"type": event_subtype or event_type, "event": event})
    # ...
```

Example of Telegram event handling.
```python
def _setup_event_handlers(self) -> None:
    # ...
    @self.client.on(events.NewMessage())
    async def on_new_message(event):
        await self.event_callback({"type": "new_message", "event": event})
    # ...
```

Example of Zulip event handling. (Zulip employs a polling mechanism rather than event-driven callbacks.)
```python
async def start_polling(self) -> None:
    if self._polling_task is None or self._polling_task.done():
        self._polling_task = asyncio.create_task(self._polling_loop())

async def _polling_loop(self) -> None:
    # ...
    response = await loop.run_in_executor(
        None,
        lambda: self.client.get_events(queue_id=self.queue_id, last_event_id=self.last_event_id, dont_block=False)
    )
    # ...
    if response and "events" in response:
        for event in response["events"]:
            await self.process_event(event)
    # ...
```

#### Incoming Events Processor
The `IncomingEventsProcessor` is derived from an abstract parent class `BaseIncomingEventProcessor` defined in `src/core/events/processors/base_incoming_event_processor.py`. This processor acts as an intermediary between the `Adapter` and the conversation manager, enriching incoming platform events with additional context before forwarding them.

The central method of this class is `process_event`, which routes events to appropriate handlers based on their type.
```python
async def process_event(self, event: Any) -> List[Dict[str, Any]]:
    # ...
    event_handlers = self._get_event_handlers()
    handler = event_handlers.get(event["type"])
    if handler:
       return await handler(event)
    return []
    # ...
```

Each platform adapter has its own version of the class at `src/adapters/your_adapter/event_processing/incoming_event_processor.py`, defining platform-specific event handlers. For example, Zulip's implementation handles the following event types.
```python
class ZulipIncomingEventType(str, Enum):
    MESSAGE = "message"
    UPDATE_MESSAGE = "update_message"
    DELETE_MESSAGE = "delete_message"
    REACTION = "reaction"
    REALM = "realm"
    STREAM = "stream"
    FETCH_HISTORY = "fetch_history"

def _get_event_handlers(self) -> Dict[str, Callable]:
    return {
        ZulipIncomingEventType.MESSAGE: self._handle_message,
        ZulipIncomingEventType.UPDATE_MESSAGE: self._handle_update_message,
        ZulipIncomingEventType.DELETE_MESSAGE: self._handle_delete_message,
        ZulipIncomingEventType.REACTION: self._handle_reaction,
        ZulipIncomingEventType.REALM: self._handle_rename,
        ZulipIncomingEventType.STREAM: self._handle_rename,
        ZulipIncomingEventType.FETCH_HISTORY: self._handle_fetch_history
    }
```

Although all adapters process similar events (message creation/update/deletion, pinning/unpinning, and reaction changes), each platform's unique data structures necessitate custom handling methods. The exceptions are history fetching and rename events (when a Discord server, Slack team, or Zulip channel changes its name), which share common logic defined in the base class.

Before sending events to the conversation manager, the processor may preprocess them, particularly for new or updated messages (see Event Preprocessing). After processing, the `Manager` returns a delta of changes to the `IncomingEventProcessor`. The processor checks if additional actions are needed (such as history fetching), then generates a set of internal events that are returned to the `Adapter`. These events are sent to Connectome and the LLM via the `SocketIOServer` using Pydantic models (see details on event generation and Pydantic model usage).

To add support for a new incoming event type, several changes are required:
1. Update the `Client` class if necessary to track the new event
2. Add the new event to the `IncomingEventType` enum at the beginning of `src/adapters/your_adapter/incoming_event_processor.py`
3. Add a new handler to the handlers dictionary in the same file
4. Implement a handler method for the new event
5. Make any other necessary changes to support the new event type  (see "Event Communication and Pydantic Models")

#### Incoming Event Preprocessing
This preprocessing typically involves two steps:
1. Attachment Download. Using the `Downloader` class (defined in `src/adapters/your_adapter/event_processing/attachment_loaders/downloader.py`), the processor downloads any attachments included in the message. This step is always performed for new messages, while for message updates, it depends on the platform's capabilities - Zulip allows adding new attachments during edits, whereas Telegram does not.
2. User Information Processing. Through the `UserInfoPreprocessor` (defined in `src/adapters/your_adapter/event_processing/user_info_preprocessor.py`), the processor updates the `UserCache` with information about the message author (only for new messages) and any mentioned users (for new and updated messages). It also standardizes user mentions in the text, replacing platform-specific formats with a unified `<@{user.display_name}>` tag.

#### Conversation Management
The `Manager` class (with abstract parent class `BaseManager` defined in `src/core/conversation/base_manager.py`) tracks all active conversations and manages their state. Each conversation is stored as an instance of `ConversationInfo` with the following key attributes:
```python
conversation_id: str                     # Unique ID generated for adapter and connectome use
platform_conversation_id: str            # Platform-specific ID used to identify conversations
conversation_type: str                   # Platform-dependent type (e.g., "private", "stream", "dm", "channel")
conversation_name: Optional[str] = None  # Name from platform or auto-generated for unnamed conversations
server_id: Optional[str] = None          # Platform server identifier (varies by platform)
server_name: Optional[str] = None        # Human-readable server name
created_at: datetime = None              # When this conversation was first observed
last_activity: datetime = None           # Timestamp of last message
known_members: Set[str] = field(default_factory=set)       # IDs of conversation participants
just_started: bool = False                                 # Flag for new conversations requiring history
threads: Dict[str, ThreadInfo] = field(default_factory=dict)    # Thread information
attachments: Set[str] = field(default_factory=set)              # Attachment IDs in this conversation
```

The `Manager` class provides several key methods:
* `conversation_exists` checks if a conversation exists based on an event
* `get_conversation` retrieves a cached conversation by ID
* `get_conversation_cache`, gets cached messages for a conversation in dictionary format
* `add_to_conversation` adds a new message to a conversation
* `update_conversation` updates existing messages in a conversation
* `delete_from_conversation` removes messages from a conversation

The Manager's architecture organizes event handling around three primary methods (`add_to_conversation`, `update_conversation`, and `delete_from_conversation`), which handle most incoming events. This structure reflects how platforms handle message-related events - all clearly distinguish new and deleted messages, but some treat edits, reactions, and pin/unpin operations as separate events while others group them under message updates and issue the same event for all of them (for example, Telegram will issue the same `edited_message` message event for the change of message text, the addition of a new reaction and for the removal of existing one; Discord will issue the same event in case of the change of message text and of the change of its pin status). The base class defines the logical flow for these methods, while platform-specific details are implemented in subclasses.

##### Message Addition Flow
When a new message arrives, the `add_to_conversation` method does the following things in exactly that order:
1. Checks if the conversation is new, and if so, registers it with a new `ConversationInfo` instance using `_get_or_create_conversation_info`
2. Uses `ThreadHandler` (base class in `src/core/conversation/base_thread_handler.py` with platform-specific implementations in `src/adapters/your_adapter/conversation/thread_handler.py`) to track if the message belongs to a thread
3. Creates and caches the message via `_create_message`, which uses `MessageBuilder` to extract message details from the platform-specific event
4. Processes attachment information and updates both the conversation and `AttachmentCache`
5. Generates a `ConversationDelta` that summarizes the changes to report to Connectome and the LLM

##### Message Update Flow
The `update_conversation` method:
1. Searches for the relevant conversation (returning early if none is found)
2. Calls the platform-specific `_process_event` method to handle changes like reaction updates, pin/unpin status, or text edits
3. Generates a `ConversationDelta` to report changes

##### Message Deletion Flow
The `delete_from_conversation` method:
1. Searches for the existing conversation (returning early if none exists)
2. Locates and removes the specified messages
3. Updates related data like threads and pinned message lists
4. Generates a `ConversationDelta` to report the changes

#### History Fetching
History fetching is handled by the `HistoryFetcher` class, which extends the abstract `BaseHistoryFetcher` defined in `src/core/events/history_fetcher/base_history_fetcher.py`. This class operates in two modes:
* Cache-based fetching. Retrieves history from the message cache (implemented in the base class and shared across all adapters)
* API-based fetching. Sends requests to the platform API when cached history is insufficient or unavailable (implemented in platform-specific classes at `src/adapters/your_adapter/event_processing/history_fetcher.py`)

#### Outgoing Events Processor
The `OutgoingEventsProcessor` extends an abstract parent class `BaseOutgoingEventProcessor` defined in `src/core/events/processors/base_outgoing_event_processor.py`. This processor handles events flowing from Connectome to the platform, ensuring they are properly formatted and executed according to each platform's requirements.

Unlike incoming events, which vary across platforms, outgoing events follow a standardized structure defined in the base class. This standardization allows Connectome to interact with different platforms using a consistent interface. The base class defines a comprehensive set of outgoing event types that are common across all platforms.
```python
class OutgoingEventType(str, Enum):
    SEND_MESSAGE = "send_message"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    ADD_REACTION = "add_reaction"
    REMOVE_REACTION = "remove_reaction"
    FETCH_HISTORY = "fetch_history"
    FETCH_ATTACHMENT = "fetch_attachment"
    PIN_MESSAGE = "pin_message"
    UNPIN_MESSAGE = "unpin_message"
```
The `rocess_event method` routes these events to appropriate handlers.
```python
async def process_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
    # ...
    event_handlers = {
        OutgoingEventType.SEND_MESSAGE: self._handle_send_message_event,
        OutgoingEventType.EDIT_MESSAGE: self._handle_edit_message_event,
        OutgoingEventType.DELETE_MESSAGE: self._handle_delete_message_event,
        OutgoingEventType.ADD_REACTION: self._handle_add_reaction_event,
        OutgoingEventType.REMOVE_REACTION: self._handle_remove_reaction_event,
        OutgoingEventType.FETCH_HISTORY: self._handle_fetch_history_event,
        OutgoingEventType.FETCH_ATTACHMENT: self._handle_fetch_attachment_event,
        OutgoingEventType.PIN_MESSAGE: self._handle_pin_event,
        OutgoingEventType.UNPIN_MESSAGE: self._handle_unpin_event
    }
    outgoing_event = self.outgoing_event_builder.build(data)
    handler = event_handlers.get(outgoing_event.event_type)
    return await handler(outgoing_event.data)
    # ...
```
Each event type has a corresponding handler method in the base class that provides common error handling and logging. These handlers delegate to abstract methods that must be implemented by platform-specific subclasses.
```python
async def _handle_delete_message_event(self, data: BaseModel) -> Dict[str, Any]:
    try:
        return await self._delete_message(self._find_conversation(data.conversation_id), data)
    except Exception as e:
        logging.error(f"Failed to delete message {data.message_id}: {e}", exc_info=True)
        return {
            "request_completed": False,
            "error": f"Failed to delete message: {e}"
        }

@abstractmethod
async def _delete_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
    raise NotImplementedError("Child classes must implement _delete_message")
```
Meanwhile, each platform implements the abstract methods differently to accommodate its unique API requirements. For example, the `_delete_message` method has distinct implementations across platforms.

Zulip Implementation
```python
async def _delete_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
    await self.rate_limiter.limit_request("delete_message", data.conversation_id)
    self._check_api_request_success(
        self.client.call_endpoint(f"messages/{int(data.message_id)}", method="DELETE"),
        "delete message"
    )
    return {"request_completed": True}
```

Slack Implementation
```python
async def _delete_message(self, conversation_info: Any, data: BaseModel) -> Dict[str, Any]:
    channel_id = conversation_info.platform_conversation_id.split("/")[-1]
    await self.rate_limiter.limit_request("delete_message", data.conversation_id)
    response = await self.client.chat_delete(channel=channel_id, ts=data.message_id)
    if not response.get("ok", None):
        raise Exception(f"Failed to delete message: {response['error']}")
    logging.info(f"Message {data.message_id} deleted successfully")
    return {"request_completed": True}
```

When processing outgoing messages that include files, the system uses the `Uploader` class defined in `src/adapters/your_adapter/event_processing/attachment_loaders/uploader.py`. This component handles the platform-specific requirements for file uploads. While most platforms only support file uploads with new messages, some (like Zulip) also allow adding files during message edits.

Another important point to make: in most cases, when the outgoing event is processed, there is no need to modify caches from the `OugoingEventProcessor` side (the `Client` will receive a relevant event, and the `IncomingEventProcessor` will handle it). However, this is not true in case with Telegram. There, it is necessary to process the outgoing event, then to call `Manager` from the `OugoingEventProcessor` side and record changes.

To add support for a new outgoing event type, several changes are required:
1. Add the new event to the `OutgoingEventType` enum in `src/core/events/processors/base_outgoing_event_processor.py`
2. Add a new handler method to the base class
3. Define an abstract method that platform-specific implementations must provide
4. Implement the platform-specific method in each adapter's outgoing event processor
5. Update the Pydantic models to support the new event type (see "Event Communication and Pydantic Models")

An important consideration when adding new event types is cross-platform compatibility. Since Connectome expects to receive/send the same events regardless of which adapter it's communicating with, any new event should be supported by most or all platforms.

Before implementing a new event type, developers should:
1. Verify that the functionality is supported by most target platforms
2. Consider how to gracefully handle platforms that don't support the functionality
3. Weigh the benefits of adding platform-specific functionality against the complexity of maintaining different capabilities across adapters

For example, pin/unpin functionality might be omitted for platforms like Zulip that don't support it, but a feature only available on a single platform might not justify the additional complexity across the entire adapter ecosystem. This standardized approach to outgoing events ensures that Connectome can interact with multiple platforms through a consistent interface, while the platform-specific implementations handle the unique requirements of each platform's API.

#### Event Communication and Pydantic Models
The adapter system uses structured events to communicate with Connectome and LLMs. These events fall into three main logical categories:
1. Connection Status Events. Connection events inform Connectome about the adapter's operational status:
* `connect`. Sent periodically to indicate the adapter is active and functioning
* `disconnect`. Sent when the adapter loses connection or is shutting down
These status updates ensure that Connectome always has current information about the availability of communication channels.
2. Incoming Platform Events
These events report changes that occur on the platform side and are captured by the adapter:
* `message_received`. A new message has been posted
* `message_updated`. An existing message has been edited
* `message_deleted`. A message has been removed
* `reaction_added`. A reaction has been added to a message
* `reaction_removed`. A reaction has been removed from a message
* `message_pinned`. A message has been pinned in a conversation
* `message_unpinned`. A message has been unpinned from a conversation
* `history_fetched`. Message history has been retrieved
* `conversation_started`. A new conversation has begun
* `conversation_updated`. Conversation metadata has changed
The `IncomingEventProcessor` generates these events, which are then emitted by the `Adapter` when the relevant platform event triggers a listener.
Both connection status and incoming platform events are sent to Connectome where they are captured by the event handler
```python
@client.on("bot_request")
```
defined in `connectome/host/modules/activities/activity_client.py`. The adapter emits these events without tracking their reception or handling; it simply provides the information for any component that needs it.
3. System Events. System events facilitate the processing of outgoing events (requests from Connectome to the platform). When an LLM sends a request, the adapter's SocketIOServer captures it using:
```python
@self.sio.event
async def bot_response(sid, data):
```
During processing, the adapter emits system events to inform Connectome about the request's status:
* `request_queued`. Sent when the request has been received and is being processed
* `request_success`. Sent when the request has been successfully completed
* `request_failed`. Sent when the request encountered an error or could not be completed

These system events create a feedback loop that keeps Connectome informed about the progress and outcome of its requests to the platform. They are captured by separate event handlers in `connectome/host/modules/activities/activity_client.py`.

To ensure consistent and well-structured event data, the adapter system uses Pydantic models. These models define the structure, validation rules, and documentation for each event type. The models are organized in the following files:
* `src/core/events/models/connection_events.py`, models for connect and disconnect events
* `src/core/events/models/incoming_events.py`, models for platform change events
* `src/core/events/models/outgoing_events.py`, models for payloads received from Connectome
* `src/core/events/models/request_events.py`, models-wrappers applied to the events before communicating them to Connectome
Corresponding builder classes in `src/core/events/builders/` help construct properly formatted events based on these models.

When adding a new event type as mentioned above, developers must:
1. Define the event's structure by creating or modifying the appropriate Pydantic model
2. Create or update the corresponding builder class to construct events of this type

This structured approach ensures that:
* Events have consistent, well-defined formats
* Data validation occurs at the model level
* Documentation of event structures is built into the code
* Both sending and receiving components understand the event format

#### socket.io Server
The `SocketIOServer` class, found in `src/core/socket_io/server.py`, serves as the critical communication bridge between the adapter and Connectome. Its primary responsibility is to manage the orderly exchange of events through Socket.IO, ensuring reliable bidirectional communication.

When initialized, the SocketIOServer registers several key event handlers:
```python
@self.sio.event
async def connect(sid, environ):
    # Handle new connection establishment to adapter, nothing to do with the connect event from above
    # ...
@self.sio.event
async def disconnect(sid):
    # Handle disconnection from adapter, nothing to do with the disconnect event from above
    # ...
@self.sio.event
async def cancel_request(sid, data):
    # Handle request cancellation
    # ...
@self.sio.event
async def bot_response(sid, data):
    # Handle incoming responses from the LLM
    # ...
```
These handlers ensure that the server responds appropriately to connection events and requests from Connectome.

The server provides two primary lifecycle methods:
* `start()`. Initializes and starts the Socket.IO server
* `stop()`. Gracefully shuts down the server and cleans up any pending requests

For sending events to Connectome and LLMs, the server provides specialized methods: `emit_event()`, `emit_request_queued_event()`, `emit_request_failed_event()`, `emit_request_success_event()`.

When Connectome sends a request to the adapter, the server follows a structured processing flow:
* Request Queueing. Upon receiving a request via the `bot_response` event, the server queues it internally using the `_queue_event` method and emits a `request_queued` event to acknowledge receipt.
* Asynchronous Processing. The server maintains a processing loop that handles queued events one by one through the `_process_single_event` method. This approach prevents request overload and ensures orderly processing.

The server first checks if it's in the process of shutting down. If so, it emits a `request_failed` event to prevent processing during shutdown.
It then forwards the outgoing event to the adapter for execution and awaits the result. Upon receiving the result, it transforms it into an appropriate request event. Finally, it emits the result back to Connectome.

The server supports request cancellation through the `cancel_request` event, which is processed by the `_cancel_request` method. When a cancellation is requested, the server attempts to locate and remove the specified request from its queue. If the request is found and successfully removed, the server emits a `request_success` event. If the request cannot be found (perhaps because it's already being processed), the server emits a `request_failed` event.

During server shutdown, the system ensures no requests are left unhandled by emitting a `request_failed` event for all queued requests.
