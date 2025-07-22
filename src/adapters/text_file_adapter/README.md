# Text File Adapter Documentation

### Purpose
The Text File Adapter serves as a bridge between LLMs and the local filesystem, enabling direct file operations through a simple, command-based interface. Unlike UI-focused tools that require diff visualization, this adapter provides pure functionality—creating, reading, modifying, and deleting files. This adapter facilitates:
* Manage configuration files
* Generate and modify code files
* Create documentation
* Process and transform data files
* Organize information in a persistent manner

### File System Integration
The adapter uses Python's built-in file system libraries to interact with local files:
* os module: For file and directory operations
* pathlib: For modern path manipulation
* shutil: For high-level file operations

### Architecture Overview
The adapter operates exclusively on the host OS where the adapter is running. It executes with root-level permissions within a defined scope.

#### Communication Protocol
The adapter communicates through socket.io, following the established pattern with `bot_response` events. Incoming Request Structure:
```python
{
  "event_type": "command_name",
  "data": {
    # Command-specific parameters
  }
}
```

Response Types:
```python
{
  "request_success": {
    "adapter_type": "file",
    "request_id": "uuid-string",
    # Additional command-specific data
  }
}
{
  "request_queued": {
    "adapter_type": "file",
    "request_id": "uuid-string"
  }
}
{
  "request_failed": {
    "adapter_type": "file",
    "request_id": "uuid-string"
  }
}
```

#### Supported Operations
| Command | Required Inputs | Description |
|---------|-----------------|-------------|
| view | Path to directory `path` (str) | Lists all files and subdirectories in the specified directory |
| read | Path to file `path` (str), Lines to read `view_range` (list[int], optional) | Returns the content of the specified file |
| create | Path to file `path` (str), Content `content` (str) | Creates a new file with the provided content |
| delete | Path to file `path` (str) | Removes the specified file from the filesystem |
| move | Path to file `source_path` (str), New path `destination_path` (str) | Relocates a file to a different directory or changes its name |
| update | Path to file `path` (str), New content `content` (str) | Replaces the entire content of an existing file |
| insert | Path to file `path` (str), Text to insert `content` (str), Line number `line` (int) | Adds text at a specific position in the file |
| replace | Path to file `path` (str), Old text `old_string` (str), New text `new_string` (str) | Performs case-sensitive string replacement within a file |
| undo | Path to file `path` (str) | Reverts the most recent modification to the specified file |

#### Security Features
The Text File Adapter implements several security measures:
* File Validation. Checks file types, sizes, and extensions
* Directory Restrictions. Limits operations to specified directories
* Size Limitations. Prevents operations on files exceeding size limits
* Backup System. Creates backups before modifying files to support undo operations

#### Adapter Specific Features
1) Path Handling. Supports both absolute and relative paths. Relative paths are resolved against the base directory. Absolute paths are checked against allowed directories. Both are sanitized. For move operations both paths should end with file names (either for renaming or moving). For example:
```python
{
  "event_type": "move",
  "data": {
    "source_path": "/home/user/documents/file.txt",
    "destination_path": "/home/user/documents/renamed_file.txt"
  }
}
```
```python
{
  "event_type": "move",
  "data": {
    "source_path": "/home/user/documents/tmp/file.txt",
    "destination_path": "/home/user/documents/another_tmp/file.txt"
  }
}
```
2) Undo Capability. Maintains a history of file changes. Create, update, insert, replace, and delete operations can be undone because their backups are stored in the backup directory. Move operations are not undoable. Important to add, automatic cleanup prevents accumulation of old backups.
3) Text File Focus. Optimized for working with text files. Checks if files are valid text files, detects binary files and prevents operations on them, and uses UTF-8 encoding for all text operations. Reading size limits are necessary to avoid overwhelming the LLM's context window, meanwhile for writing files we use a much lighter validation approach because of natural constraints of LLMs (context window size, text-based nature of their outputs, and the communication channel's own practical limits).
4) Encoding and Format. In this adapter there is no base64 encoding similar to platform adapter. We deal with text files only, so we read the content and submit it to the connectome framework without any formatting. We also accept the content from the framework and use it to create/update files without any transformations.

### Code structure
For better understanding of the code structure, it is recommended to read the [PLatform Adapters Code Structure](https://github.com/antra-tess/connectome-adapters/blob/master/docs/code_structure.md) first.

#### Adapter
The Text File Adapter differs from platform adapters in that it interacts directly with the file system rather than an external communication platform. It reuses key components from the core adapter architecture:
* `src/core/utils/config.py`. Manages adapter settings and configuration
* `src/core/socket_io/server.py`. Handles communication with Connectome

Like other adapters, the Text File Adapter has a main entry point defined in `src/adapters/text_file_adapter/main.py`. This script performs the essential initialization steps:
* Sets up logging for the adapter
* Initializes and starts the Socket.IO server
* Creates and starts the Text File Adapter instance

The `Adapter` class, defined in `src/adapters/text_file_adapter/adapter.py`, follows the same basic structure as platform adapters.
* The class implements `start()` and `stop()` methods for lifecycle management
* It includes a `_monitor_connection` method, but unlike platform adapters, it doesn't need to check a client connection

The `Adapter` has several important distinctions from platform adapters:
* No External Client. Since the adapter interfaces directly with the operating system, there is no external platform client to connect to or monitor. The adapter itself is the endpoint for all requests.
* Always Connected. From Connectome's perspective, the Text File Adapter is always in a connected state as long as the adapter is running. It doesn't need to establish or maintain connections to external services.
* Unidirectional Event Flow. The Text File Adapter primarily processes outgoing events (requests from Connectome to execute file operations). It doesn't listen for or react to spontaneous changes in the file system environment.
* Connection Status. Although the adapter still emits `connect` and `disconnect` events to maintain protocol consistency with other adapters, these events simply reflect the running state of the adapter itself rather than a connection to an external service.

#### Event Processing
Unlike platform adapters, the Text File Adapter uses a single processor class called `Processor`, defined in `src/adapters/text_file_adapter/event_processing/processor.py`. This processor handles all event types without inheriting from `BaseOutgoingEventProcessor`, reflecting its unique purpose and operation. The independence from the standard base class gives the Text File Adapter more flexibility in defining its event types and handling methods, though it still maintains a structured approach using Pydantic models for event payloads (defined in `src/adapters/text_file_adapter/event_processing/outgoing_events.py`).

The Text File Adapter's processor supports a focused set of event types specifically designed for file operations.
```python
class FileEventType(str, Enum):
    """Event types supported by the OutgoingEventProcessor"""
    VIEW = "view"
    READ = "read"
    CREATE = "create"
    DELETE = "delete"
    MOVE = "move"
    UPDATE = "update"
    INSERT = "insert"
    REPLACE = "replace"
    UNDO = "undo"
```

Despite its architectural differences, the processor follows a similar event handling pattern to other adapters.
```python
async def process_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
    event_handlers = {
        FileEventType.VIEW: self._handle_view_event,
        FileEventType.READ: self._handle_read_event,
        FileEventType.CREATE: self._handle_create_event,
        FileEventType.DELETE: self._handle_delete_event,
        FileEventType.MOVE: self._handle_move_event,
        FileEventType.UPDATE: self._handle_update_event,
        FileEventType.INSERT: self._handle_insert_event,
        FileEventType.REPLACE: self._handle_replace_event,
        FileEventType.UNDO: self._handle_undo_event
    }
    outgoing_event = self.outgoing_event_builder.build(data)
    handler = event_handlers.get(outgoing_event.event_type)
    return await handler(outgoing_event.data)
```

#### File Validation
While executing reading file operations, the adapter uses a `FileValidator` class, defined in `src/adapters/text_file_adapter/event_processing/file_validator.py`. When the processor receives a file path from Connectome, this validator ensures that accessing the file is both possible and permissible according to configured security policies.

The validator performs several important checks:
* Existence Check. Verifies that the specified file actually exists in the file system
* File Type Validation. Ensures the file extension meets the configured security policy
* Text File Verification. Confirms that the file contains text content that can be safely processed
* Length Check. Validates that the file size is within acceptable limits

The validator implements three levels of security that can be configured through the `security_mode` setting in the "adapter" category.
```python
class SecurityMode(str, Enum):
    """Security modes supported by the FileValidator"""
    STRICT = "strict"
    PERMISSIVE = "permissive"
    UNRESTRICTED = "unrestricted"
```
In `UNRESTRICTED` mode, the validator allows reading any textual file regardless of its extension. This provides maximum flexibility but should only be used in trusted, controlled environments. In `PERMISSIVE` mode, the validator checks if the file extension appears in a configurable `blocked_extensions` list (from the "adapter" category). Files with extensions on this list are rejected, while all others are permitted. This implements a "deny list" approach to security. In `STRICT` mode, the validator only allows files with extensions that appear in a configurable `allowed_extensions` list (from the "adapter" category). This implements an "allow list" approach, which is the most secure option as it explicitly defines which file types can be accessed.

If any validation check fails, the validator raises an `Exception` with a descriptive error message, preventing the operation from proceeding. This ensures that potentially unsafe file operations are blocked before they can be executed.

#### File Event Cache
The `FileEventCache`, defined in `src/adapters/text_file_adapter/event_processing/file_event_cache.py`, provides a powerful version control and undo system for file operations triggered by Connectome. By tracking changes and maintaining backups, it enables safe file manipulation with the ability to revert unwanted changes.

When the `Processor` handles a file operation request from Connectome, the `FileEventCache` implements a three-step process:
1. Backup Creation. Before any modification, the system creates a backup of the file in its current state
2. Operation Execution. The requested operation (edit, delete, etc.) is performed
3. Event Recording. The operation details are added to a stack of cached events for potential future undo operations

If an undo request is received, the system simply:
1. Retrieves the most recent event from the stack
2. Locates the corresponding backup file
3. Restores the file to its previous state

Several important aspects of the cache behavior can be configured in the "adapter" category:
* `backup_directory` specifies where backup files should be stored
* `event_ttl_hours` defines how long events remain valid before automatic cleanup
* `cleanup_interval_hours` sets how frequently the system checks for and removes expired events
* `max_events_per_file` limits how many operations can be tracked for a single file

The last setting is particularly important for frequently modified files, as it prevents the cache from growing excessively large while maintaining a reasonable history depth.

The FileEventCache implements lifecycle management through
* `start` method that initializes the cache and begins the background cleanup process
* `stop` method that cancels the background task and removes all backups

Importantly, when the adapter restarts, it begins with a clean slate - an empty backup directory and cache. This ensures that each adapter session maintains its own independent history.

The cache provides specialized methods for different operation types.
* `record_create_event` tracks file creation
* `record_update_event` tracks file modifications
* `record_delete_event` tracks file deletion
* `record_move_event` tracks file relocation
* `undo_recorded_event` reverts the most recent operation

An important limitation to note is that `move` operations cannot be undone. This is because moving a file changes its absolute path, which is used as a key identifier in the event cache. Once a file's path changes, any previous events associated with the old path become invalid for undo operations.

### Configurations
The Text File Adapter is configured through a YAML file with the following settings:

```yaml
adapter:
  adapter_type: "text_file"                       # Adapter type
  connection_check_interval: 300                  # Seconds to check connection
  max_file_size: 5                                # Maximum file size in MB
  max_token_count: 10000                          # Maximum token count for text files
  security_mode: "strict"                         # Security mode: strict, permissive, unrestricted
  allowed_extensions:                             # List of allowed file extensions
    - "txt"
  blocked_extensions:                             # List of blocked file extensions
    - "exe"
    - "dll"
    - "bin"
  backup_directory: "backups/text_file_adapter"   # Directory for file backups
  event_ttl_hours: 2                              # Hours to keep events in cache
  cleanup_interval_hours: 1                       # Hours to clean up expired events
  max_events_per_file: 10                         # Maximum events to store per file
  base_directory: "adapters/text_file_adapter"    # Base directory for relative paths
  allowed_directories:                            # List of allowed directories for absolute paths
    - "/home/user"

logging:
  logging_level: "info"                           # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_file_path: "logs/text_file_adapter.log"
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_log_size: 5242880                           # Maximum log file size in bytes
  backup_count: 3                                 # Number of log file backups to keep

socketio:
  host: "127.0.0.1"                               # Socket.IO server host
  port: 8086                                      # Socket.IO server port
  cors_allowed_origins: "*"                       # CORS allowed origins
```




