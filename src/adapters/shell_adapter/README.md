# Shell Adapter Documentation (currently only partially done; LLM confirmation loop required to be completed)

### Purpose

The Shell Adapter is cross-platform; it is designed to enable LLMs to execute shell commands. It provides a bridge between the LLM and the operating system's command-line interface, allowing for automation, system diagnostics, development tasks, and other command-line operations. The adapter is built in such a way that LLMs may cause some environment "trashing", but provides mechanisms to detect and prevent such situations.

### Core Functionality

The adapter supports two execution modes:
* Independent Execution. Commands run independently without persistent state. Environment reset between commands.
* Session-Based Execution. Maintains persistent shell session with state. Preserves environment variables, working directory. Allows multi-step operations with state dependencies.

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
