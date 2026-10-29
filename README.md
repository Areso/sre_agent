# SRE agent

Interactive agent: a local Ollama model diagnoses Linux servers over SSH using the
[safe-ssh-mcp](https://github.com/Areso/safe-ssh-mcp) read-only tools.

## Requirements
- [uv](https://docs.astral.sh/uv/) (also provides `uvx`, used to launch the MCP server)
- Ollama running locally, with a model that supports tool calling
- SSH key access to the target hosts; each host must already be in `~/.ssh/known_hosts`

## Run
```bash
uv sync
uv run agent.py
```
Then ask, e.g. `check whether fr1.areso.pro is okay: CPU, load, disk, failed units`.
Quit with `exit`, Ctrl+C or Ctrl+D.

On startup the agent checks that Ollama is reachable and that the configured model
exists and supports tool calling (and thinking, if enabled), and exits with a clear
message otherwise.

## Configuration
Everything lives in `agent_config.ini`. Every key is required, except that only the
selected transport needs its own setting (`mcp_stdio_command` or `mcp_server_url`).
- `mcp_transport`: `stdio` (launch the server) or `sse` (connect to a running one)
- `mcp_stdio_command`: how to launch the MCP server (pinned PyPI version, or a local checkout for development)
- `mcp_server_url`: server URL, used with `sse`
- `ollama_model`, `ollama_think`: model and whether it reasons before answering
- `default_ssh_user`, `default_ssh_key`: used when the model doesn't specify them
- `log_prompts`, `log_responses`, `log_tools`: write requests and responses to `prompts/`

If the SSH key has a passphrase, export `SSH_KEY_PASSPHRASE` before starting.

## TODO
- Migrate to `mcp` 2.x (`Tool.inputSchema` → `Tool.input_schema`).
