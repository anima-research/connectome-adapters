# Shell Adapter Documentation (currently only partially done; LLM confirmation loop required to be completed)

### Purpose
The Shell Adapter is cross-platform; it is designed to enable LLMs to execute shell commands. It provides a bridge between the LLM and the operating system's command-line interface, allowing for automation, system diagnostics, development tasks, and other command-line operations. The adapter is built in such a way that LLMs may cause some environment "trashing", but provides mechanisms to detect and prevent such situations.

### Architecture Overview

The adapter exposes the following primary endpoints:
* `open_session` create persistent shell session
* `execute_command`	runs shell command
* `close_session`	terminates session
* `shell_metadata`	gets system information	(including the details of OS)

To run a single command it is enough to use `execute_command`; it will open a new session, execute your command, then close this temporary session. Meanwhile, to run a sequence of commands in a same session, it is necessary to open a new session first via `open_session`, then execute commands inside that session (`execute_command` should be run N times, where N is the number of commands you want to execute), then close that session with `close_session`.

The command output captured during `execute_command` is returned fully, and it is structured for clear interpretation:
```json
{
  "stdout": "Standard output text",
  "stderr": "Error output text",
  "exit_code": 0
}
```
For long outputs, the adapter will trim to configurable limits of output. It will preserve its beginning and end portions as well as provide a clear indication of truncation.

The summary of commands and their input/output is provided in a table below.
| Event Type           | Input Data                              | Output Data                                                          |
|----------------------|-----------------------------------------|----------------------------------------------------------------------|
| open_session | {} |{ "session_id": str }|
| close_session | { "session_id": str } |{ "session_id": str }|
| execute_command | { "command": str, "session_id": Optional[str] } |{ <br>&nbsp;&nbsp;"stdout": str, <br>&nbsp;&nbsp;"stderr": str, <br>&nbsp;&nbsp;"exit_code": int, <br>&nbsp;&nbsp;"original_stdout_size": int, <br>&nbsp;&nbsp;"original_stderr_size": int, <br>&nbsp;&nbsp;}|
| shell_metadata | {} |{ <br>&nbsp;&nbsp;"operating_system": str, <br>&nbsp;&nbsp;"shell": str, <br>&nbsp;&nbsp;"workspace_directory": str <br>&nbsp;&nbsp;}|

Resource usage is monitored and limited, i.e. the adapter performs background monitoring of CPU, memory, disk usage and terminates those sessions that use too much resources. It is possible to configure thresholds for resource limits.

### Examples of event flow

The adapter receives `shell_metadata` and returns information about the environment. Response is shown below.
```json
{
  "operating_system": "Ubuntu 22.04.3 LTS",
  "shell": "bash GNU bash, version 5.1.16(1)-release (x86_64-pc-linux-gnu)",
  "workspace_directory": "/home/user"
}
```

Then, it receives `open_session` request, creates a new session and returns its ID. Response is shown below.
```json
{
  "session_id": "session_ID_uniq_1"
}
```

Then, the adapter receives `execute_command` request that contains command to execute (for example, `cat test.log`) and the ID of session opened before (in our case, `session_ID_uniq_1`). It returns the output. (Notice, that original size of outputs is equivalent to `len(output)`.) Response is shown below.
```json
{
  "stdout": "hello from test.log file",
  "stderr": "",
  "exit_code": 0,
  "original_stdout_size": 23,
  "original_stderr_size": 0
}
```

### Code structure
For better understanding of the code structure, it is recommended to read the [PLatform Adapters Code Structure](https://github.com/antra-tess/connectome-adapters/blob/master/docs/code_structure.md) first.

#### Adapter
The Shell Adapter differs from platform adapters in that it interacts directly with the operating system rather than an external communication platform. It enables LLMs to execute shell commands and interact with the local environment, serving as a terminal interface for AI systems.

The Shell Adapter reuses key components from the core adapter architecture:
* `src/core/utils/config.py`. Manages adapter settings and configuration
* `src/core/socket_io/server.py`. Handles communication with Connectome

Like other adapters, the Shell Adapter has a main entry point defined in `src/adapters/shell_adapter/main.py`. This script performs the essential initialization steps:
* Sets up logging for the adapter
* Initializes and starts the Socket.IO server
* Creates and starts the Shell Adapter instance

The shell `Adapter` class, defined in `src/adapters/shell_adapter/adapter.py`, follows the same basic structure as platform adapters.
* The class implements `start()` and `stop()` methods for lifecycle management
* It includes a `_monitor_connection` method, but unlike platform adapters, it doesn't need to check a client connection

The shell `Adapter` has several important distinctions from platform adapters:
* No External Client. Since the adapter interfaces directly with the operating system, there is no external platform client to connect to or monitor. The adapter itself is the endpoint for all requests.
* Always Connected. From Connectome's perspective, the Shell Adapter is always in a connected state as long as the adapter is running. It doesn't need to establish or maintain connections to external services.
* Unidirectional Event Flow. The Shell Adapter primarily processes outgoing events (requests from Connectome to execute shell commands). It doesn't listen for or react to spontaneous changes in the operating system environment.
* Connection Status. Although the adapter still emits `connect` and `disconnect` events to maintain protocol consistency with other adapters, these events simply reflect the running state of the adapter itself rather than a connection to an external service.

#### Event Processing
Unlike platform adapters, the Shell Adapter uses a single processor class called `Processor`, defined in `src/adapters/shell_adapter/event_processing/processor.py`. This processor handles all event types without inheriting from `BaseOutgoingEventProcessor`, reflecting its unique purpose and operation. The independence from the standard base class gives the Shell Adapter more flexibility in defining its event types and handling methods, though it still maintains a structured approach using Pydantic models for event payloads (defined in `src/adapters/shell_adapter/event_processing/outgoing_events.py`).

The Shell Adapter's processor supports a focused set of event types specifically designed for shell interaction.
```python
class ShellEventType(str, Enum):
    """Event types supported by the OutgoingEventProcessor"""
    OPEN_SESSION = "open_session"
    CLOSE_SESSION = "close_session"
    EXECUTE_COMMAND = "execute_command"
    SHELL_METADATA = "shell_metadata"
```

Despite its architectural differences, the processor follows a similar event handling pattern to other adapters.
```python
async def process_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
    event_handlers = {
        FileEventType.OPEN_SESSION: self._handle_open_session_event,
        FileEventType.CLOSE_SESSION: self._handle_close_session_event,
        FileEventType.EXECUTE_COMMAND: self._handle_execute_command_event,
        FileEventType.SHELL_METADATA: self._handle_shell_metadata_event,
    }
    outgoing_event = self.outgoing_event_builder.build(data)
    handler = event_handlers.get(outgoing_event.event_type)
    return await handler(outgoing_event.data)
```

A key feature of the Shell Adapter is its session management capability. Shell commands often depend on environment state, such as current working directory, environment variables, or previously executed commands. To accommodate this, the adapter implements a session concept with two execution modes:
1. Independent Execution. A temporary session is created for a single command and then closed, providing isolation between commands.
2. Persistent Session. A session can be explicitly opened, used for multiple commands, and then explicitly closed, preserving environment state between commands.

This approach is implemented in the `_handle_execute_command_event` method.
```python
async def _handle_execute_command_event(self, data: BaseModel) -> Dict[str, Any]:
    session_id = data.session_id
    if not session_id:
        session_id = await self.session_manager.open_session()
    result = await self.session_manager.run_command(session_id, data.command)
    if not data.session_id:
        await self.session_manager.close_session(session_id)
    return {"request_completed": True, "metadata": result}
```

The Shell Adapter also provides system information through the `_handle_shell_metadata_event` method, allowing the LLM to query details about the operating system environment. This capability helps the LLM understand the context in which commands will be executed and adapt its behavior accordingly.

#### Session Management
The Shell Session Manager, defined in `src/adapters/shell_adapter/session/manager.py`, is a critical component of the Shell Adapter that handles the lifecycle and state of terminal sessions. Initialized by the `Adapter` and passed to the `Processor`, this class maintains environment persistence and resource management for shell command execution.

The Session Manager implements its own lifecycle methods:
* `start()`. Initializes the manager and begins the background monitoring process that watches for idle or expired sessions
* `stop()`. Performs cleanup by closing all active sessions and releasing resources

A key feature of the Session Manager is its automatic session monitoring through the `_cleanup_sessions` method. This background process:
* Periodically checks all active sessions
* Identifies sessions that have been idle for too long or have exceeded their maximum lifetime
* Automatically closes these sessions to prevent resource leaks
* Removes them from the session registry

The Session Manager provides three core operations:
* `open_session()`. Opens a new shell session and returns its ID
* `close_session()`. Closes an existing session by ID
* `run_command()`. Executes a command in the specified session

The method `open_session` creates a new session with a unique ID, records its creation time, and initializes it with the configured working directory from the adapter settings (`working_directory` setting in the "caching" category). When a session is no longer needed, the method `close_session`  properly closes it and removes it from the session registry. If the specified session doesn't exist, it raises a `ValueError`. Finally, the method `run_command` executes a command in the specified session via the `CommandExecutor` class. It verifies the session exists, uses the `CommandExecutor` to run the command in the session's environment, updates the session's working directory if changed by the command (e.g., after a cd command), and automatically closes the session if execution fails due to resource limits to prevent the reuse of potentially compromised environments.

#### Command Execution
The `CommandExecutor` class, defined in `src/adapters/shell_adapter/session/command_executor.py`, serves as the central controller for shell command execution. It orchestrates the execution process, handles output formatting, implements resource monitoring, and enforces system constraints to ensure safe operation.

The primary method, `execute`, takes a command string and a session instance, then creates and runs two parallel asynchronous tasks.
* `execution_task` runs the actual command via the session's `execute_command` method
* `monitoring_task` continuously monitors resource usage during execution

Once the command is executed, the the method formats and potentially truncates the command output, then returns a structured response with stdout, stderr, and execution metadata.

The `_monitor_command_resources` method implements a critical safety feature by periodically checking:
* Execution Duration. Ensures commands don't exceed the configured maximum lifetime (`command_max_lifetime` in the "adapter" category)
* CPU Usage. Monitors CPU consumption against the configured limit (`cpu_percent_limit` in the "adapter" category)
* Memory Usage. Tracks memory consumption against the configured limit (`memory_mb_limit` in the "adapter" category)

If any of these thresholds are exceeded, the executor cancels the execution task, marks the execution as failed due to resource constraints, and triggers session closure since the environment might be compromised. This proactive monitoring prevents system resource abuse, protecting against runaway processes, infinite loops, and memory leaks.

The CommandExecutor maintains awareness of all active command executions. This centralized view enables the ability to cancel all running commands during adapter shutdown. Also, it allows consistent application of resource limits and monitoring policies.

#### Session
The `Session` class, defined in `src/adapters/shell_adapter/session/session.py`, encapsulates the core functionality of an individual shell session. This class directly manages the underlying shell subprocess and provides methods for command execution and resource monitoring.

When a session is created, it doesn't immediately start a subprocess. Instead, the actual shell process is created when the `open()` method is called. This method uses `asyncio.create_subprocess_shell` to create an asynchronous shell subprocess, allowing the adapter to interact with the shell without blocking other operations. The `execute_command` method is responsible for running commands within the session's shell process. This method sends the command to the shell subprocess, captures both standard output (stdout) and standard error (stderr), and returns a structured result containing all output information. The `close` method is particularly important for resource management as it properly terminates the main shell subprocess and ensures all child processes spawned by the shell are also terminated. Another valuable feature of the `Session` class is its `get_resource_usage` method, which provides real-time information about CPU and memory usage of the session and its child processes to be used in resource monitoring done by the `CommandExecutor`.

#### Metadat Fetching
The `MetadataFetcher` class, defined in `src/adapters/shell_adapter/shell/metadata_fetcher.py`, serves as an information gathering utility that provides essential details about the execution environment. This component helps LLMs understand the system context in which commands will be executed. It collects two primary categories of information:
* Operating System Details. Gathers information about the host operating system, returning it in a standardized format:
```python
"{os_name} {os_version}" # for example, "Ubuntu 22.04.3 LTS" or "macOS 12.6.1"
```
* Shell Environment Details. Identifies the current shell and its version, returning:
```python
"{shell_type} {shell_version}" # for example, "bash GNU bash, version 5.1.16" or "zsh 5.8.1"
```

### Configuration

The Shell adapter is configured through a YAML file.
```yaml
adapter:
  adapter_type: "shell"
  connection_check_interval: 300          # in seconds
  workspace_directory: "/home/user/"      # the default directory where a new terminal starts
  session_max_lifetime: 5                 # in minutes
  command_max_lifetime: 60                # in seconds
  max_output_size: 500                    # in characters
  begin_output_size: 200                  # in characters
  end_output_size: 300                    # in characters
  cpu_percent_limit: 50
  memory_mb_limit: 50                     # in MB

logging:
  logging_level: "info"               # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_file_path: "logs/shell_adapter.log"
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_log_size: 5242880               # Maximum log file size in bytes
  backup_count: 3                     # Number of log file backups to keep

socketio:
  host: "127.0.0.1"                   # Socket.IO server host
  port: 8087                          # Socket.IO server port
  cors_allowed_origins: "*"           # CORS allowed origins
```
