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
Then ask, e.g. `check whether example.com is okay: CPU, load, disk, failed units`.
Quit with `exit`, Ctrl+C or Ctrl+D.

On startup the agent checks that Ollama is reachable and that the configured model
exists and supports tool calling (and thinking, if enabled), and exits with a clear
message otherwise.

## Example session
The model picks the tools itself; the agent fills in the SSH user and key from the config.

```text
$ uv run agent.py
🚀 Launching via STDIO: uvx safe-ssh-mcp@0.1.15 --transport stdio

SRE Agent Ready! (Using Key: id_ed25519)
Type 'exit', or press Ctrl+C / Ctrl+D to quit.

You: check CPU consumption and load average on server.example.com
   (Thinking...)
====Calling Tool: get_ps_aux_top_cpu_consumers
      Host: server.example.com | User: root | Key: ...id_ed25519
====Calling Tool: get_top
      Host: server.example.com | User: root | Key: ...id_ed25519
====Calling Tool: get_uptime
      Host: server.example.com | User: root | Key: ...id_ed25519
   (Thinking...)
```

The answer is printed as Markdown; rendered, it looks like this:

> **Agent:** Here's the status of **server.example.com**:
>
> **🚨 CPU consumption: critical**
>
> The CPU is **93.8% utilized** (almost no idle time). The main culprit:
>
> | PID | User | %CPU | %MEM | Command |
> |---|---|---|---|---|
> | **48211** | app | **96.9%** | 2.3% | `python3 /opt/app/worker.py` |
> | 1204 | mysql | 0.5% | 24.1% | `/usr/sbin/mysqld` |
> | 1317 | rabbitmq | 0.3% | 6.2% | RabbitMQ (Erlang) |
> | 1375 | app | 0.2% | 1.8% | `python3 /opt/api/server.py` |
>
> ⚠️ **`worker.py` (PID 48211)** has been running for 12 days and has accumulated
> **17,961 minutes** of CPU time. It's pinned to one core at ~97% and is very likely
> the cause of the high load.
>
> **Load average**
>
> `2.66, 2.73, 2.48` (1m, 5m, 15m): steady around 2.5–2.7, which is high for a
> small box and matches the runaway `worker.py`.
>
> **Memory**
> - Total ~1.9 GB, used 1.37 GB, free ~94 MB
> - No swap configured
> - `mysqld` uses ~24% of RAM (473 MB)
>
> **🎯 Recommendation**
> 1. Investigate what `worker.py` is doing (an infinite loop or a stuck task).
> 2. Restart it if that's safe.
>
> Would you like me to look deeper into that process or check its logs?

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

## License
MIT, see [LICENSE](LICENSE).
