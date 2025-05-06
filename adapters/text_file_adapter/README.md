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

### Implementation

The Text File Adapter implementation consists of two main components:

* Event Processor handles all file operations with validation
* File Event Cache maintains a history of file changes to support undo operations

The adapter operates exclusively on the host OS where the adapter is running. It executes with root-level permissions within a defined scope.

#### Communication Protocol

The adapter communicates through socket.io, following the established pattern with `bot_response` events. Incoming Request Structure:
```json
{
  "event_type": "command_name",
  "data": {
    // Command-specific parameters
  }
}
```

Response Types:
```json
{
  "request_success": {
    "adapter_type": "file",
    "request_id": "uuid-string",
    // Additional command-specific data
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

### Configuration

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
  backup_directory: "adapters/text_file_adapter/backups"  # Directory for file backups
  event_ttl_hours: 2                              # Hours to keep events in cache
  cleanup_interval_hours: 1                       # Hours to clean up expired events
  max_events_per_file: 10                         # Maximum events to store per file
  base_directory: "adapters/text_file_adapter"    # Base directory for relative paths
  allowed_directories:                            # List of allowed directories for absolute paths
    - "/home/user"

logging:
  logging_level: "info"                           # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_file_path: "adapters/text_file_adapter/logs/development.log"
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_log_size: 5242880                           # Maximum log file size in bytes
  backup_count: 3                                 # Number of log file backups to keep

socketio:
  host: "127.0.0.1"                               # Socket.IO server host
  port: 8086                                      # Socket.IO server port
  cors_allowed_origins: "*"                       # CORS allowed origins
```

### Supported Operations

The Text File Adapter supports a comprehensive set of file operations:

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

### Security Features

The Text File Adapter implements several security measures:

* File Validation. Checks file types, sizes, and extensions
* Directory Restrictions. Limits operations to specified directories
* Size Limitations. Prevents operations on files exceeding size limits
* Backup System. Creates backups before modifying files to support undo operations

### Text File Specific Features

1) Path Handling. Supports both absolute and relative paths. Relative paths are resolved against the base directory. Absolute paths are checked against allowed directories. Both are sanitized. For move operations both paths should end with file names (either for renaming or moving). For example:
```json
{
  "event_type": "move",
  "data": {
    "source_path": "/home/user/documents/file.txt",
    "destination_path": "/home/user/documents/renamed_file.txt"
  }
}
```
```json
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
