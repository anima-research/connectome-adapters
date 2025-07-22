# Connectome Activity adapters

See [main repository](https://github.com/antra-tess/connectome) for more information.
For details on architecture see [docs](https://github.com/antra-tess/connectome-adapters/tree/master/docs).

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
* Shell: access shell and run commands there
* Slack: communicate through Slack workspaces and channels
* Zulip: engage with Zulip streams and topics
* Text File: work with local filesystem for text file operations

### System requirements
connectome-adapters aim to be cross-platform in the long run, however, at this moment it was tested mostly on Linux. The key system requirements are:

- Python 3.11 or higher,
- pipx 1.7.0 or higher (installed with Python 3.11+)

To install `pipx`, run `python3.11 -m pip install pipx`.

### Package installation/removal
To install package, you need to perform the following steps.

1. Pull the code from Github and go into the project directory.
```bash
git clone https://github.com/antra-tess/connectome-adapters.git
cd connectome-adapters
```

2. Update the `cli/adapters.toml` file. Set those adapters that you want to be started/stopped automatically to `true`. Indicate the absolute path to the connectome-adapters project directory. (Can be done with any text file editor.)
```toml
# Adapters that are enabled/disabled
[adapters]
discord = false
discord_webhook = false
shell = false
slack = false
telegram = false
text_file = false
zulip = true

# Absolute path to the connectome-adapters project directory
project_dir = "/home/user/connectome-adapters"
```
IMPORTANT: The `project_dir` must be an absolute path to your connectome-adapters project directory. This path is used to locate all adapter-related files (logs, attachments, configs, etc.).

3. Install package using `pipx`.
```bash
python3.11 -m pipx install .
```
If you want to install package in development mode, you can do it like this.
```bash
python3.11 -m pipx install -e .
```
To verify installation, run
```bash
connectome-adapters --help
connectome-adapters status
```

4. To uninstall project you simply need to run
```bash
python3.11 -m pipx uninstall connectome-adapters
```
Then optionally delete the cloned project directory (this action is recommeneded to ensure that all attachments and logs are cleaned).

### Adapter setup
Each adapter instance handles exactly one user’s connection to a single provider (e.g., a user on Slack). The exception of rule is Discord webhook adapter. Also, each adapter runs in a separate process. One server can host many adapters, yet they require separate ports where they listen their platforms' events. To setup adapter(-s) do the following steps.

1. Go to the `connectome-adapters/config` directory.
```bash
cd your_path/connectome-adapters/config
```

2. Copy the configuration file of selected adapter and update those fields that are marked as mandatory.
```bash
cp selected_adapter_config.yaml.example selected_adapter_config.yaml
```

3. Use CLI to manage the adapter (see CLI section below).

### CLI
connectome-adapters have a CLI tool that allows to manage various adapters that run in the background. To get more details about how it works you may use
```bash
connectome-adapters --help
```
and see the list of available commands. To get more details about the specific command, please, run
```bash
connectome-adapters [command] --help
```

### Future work
* Filesystem
* WikiGraph
* MCP Host
