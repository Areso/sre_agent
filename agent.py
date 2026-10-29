import asyncio
import configparser
import json
import ollama
import os
import shlex
from datetime import datetime
from contextlib import asynccontextmanager

from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

REQUIRED_KEYS = [
    "mcp_transport", "ollama_model", "ollama_think",
    "default_ssh_user", "default_ssh_key",
    "log_prompts", "log_responses", "log_tools",
]

def load_config(path="agent_config.ini"):
    """Load settings from the ini file. It is the only source of truth: missing keys are an error."""
    config = configparser.ConfigParser()
    if not config.read(path):
        raise SystemExit(f"Config file not found: {path}")
    if "agent" not in config:
        raise SystemExit(f"Missing [agent] section in {path}")
    agent = config["agent"]

    missing = [k for k in REQUIRED_KEYS if k not in agent]
    transport = agent.get("mcp_transport", "").lower()
    if transport == "sse" and "mcp_server_url" not in agent:
        missing.append("mcp_server_url")
    elif transport == "stdio" and "mcp_stdio_command" not in agent:
        missing.append("mcp_stdio_command")
    elif transport and transport not in ("sse", "stdio"):
        raise SystemExit(f"mcp_transport must be 'sse' or 'stdio', got {transport!r}")
    if missing:
        raise SystemExit(f"Missing keys in {path}: {', '.join(missing)}")

    try:
        return {
            "mcp_transport":     transport,
            "mcp_server_url":    agent.get("mcp_server_url"),
            "mcp_stdio_command": agent.get("mcp_stdio_command"),
            "ollama_model":      agent["ollama_model"],
            "ollama_think":      agent.getboolean("ollama_think"),
            "default_ssh_user":  agent["default_ssh_user"],
            "default_ssh_key":   os.path.expanduser(agent["default_ssh_key"]),
            "log_prompts":       agent.getboolean("log_prompts"),
            "log_responses":     agent.getboolean("log_responses"),
            "log_tools":         agent.getboolean("log_tools"),
        }
    except ValueError as e:
        raise SystemExit(f"Invalid value in {path}: {e}")

_cfg = load_config()
MCP_TRANSPORT    = _cfg["mcp_transport"]
MCP_SERVER_URL   = _cfg["mcp_server_url"]
MCP_STDIO_COMMAND= _cfg["mcp_stdio_command"]
OLLAMA_MODEL     = _cfg["ollama_model"]
OLLAMA_THINK     = _cfg["ollama_think"]
DEFAULT_SSH_USER = _cfg["default_ssh_user"]
DEFAULT_SSH_KEY  = _cfg["default_ssh_key"]
LOG_PROMPTS      = _cfg["log_prompts"]
LOG_RESPONSES    = _cfg["log_responses"]
LOG_TOOLS        = _cfg["log_tools"]

def _log_prompt(action: str, prompt) -> None:
    """Write the outgoing messages list to prompts/prompt_<timestamp>.json."""
    if not LOG_PROMPTS:
        return
    try:
        os.makedirs("prompts", exist_ok=True)
        iso_time = datetime.now().isoformat().replace(":", "-").replace(".", "-")
        with open(os.path.join("prompts", f"prompt_{iso_time}.json"), "w") as f:
            json.dump({"action": action, "prompt": prompt}, f, indent=4, default=str)
    except Exception:
        pass

def _log_response(action: str, response) -> None:
    """Write the raw Ollama response to prompts/response_<timestamp>.json."""
    if not LOG_RESPONSES:
        return
    try:
        os.makedirs("prompts", exist_ok=True)
        iso_time = datetime.now().isoformat().replace(":", "-").replace(".", "-")
        if isinstance(response, dict):
            safe = response
        elif hasattr(response, "model_dump"):
            safe = response.model_dump()
        else:
            safe = str(response)
        with open(os.path.join("prompts", f"response_{iso_time}.json"), "w") as f:
            json.dump({"action": action, "response": safe}, f, indent=4, default=str)
    except Exception as e:
        print(f"Failed to log response: {e}")

def _log_tools(tools) -> None:
    """Write the tool definitions to prompts/tools_<timestamp>.json."""
    if not LOG_TOOLS:
        return
    try:
        os.makedirs("prompts", exist_ok=True)
        iso_time = datetime.now().isoformat().replace(":", "-").replace(".", "-")
        if isinstance(tools, (list, dict)):
            safe = tools
        elif hasattr(tools, "model_dump"):
            safe = tools.model_dump()
        else:
            safe = str(tools)
        with open(os.path.join("prompts", f"tools_{iso_time}.json"), "w") as f:
            json.dump({"tools": safe}, f, indent=4, default=str)
    except Exception as e:
        print(f"Failed to log tools: {e}")

@asynccontextmanager
async def get_mcp_streams():
    """Context manager to yield MCP streams based on the chosen transport."""
    if MCP_TRANSPORT == "sse":
        print(f"🔌 Connecting via SSE to {MCP_SERVER_URL}...")
        async with sse_client(MCP_SERVER_URL) as streams:
            yield streams
    elif MCP_TRANSPORT == "stdio":
        print(f"🚀 Launching via STDIO: {MCP_STDIO_COMMAND}")
        # shlex safely splits the command string into a list for subprocess
        cmd_parts = [os.path.expanduser(p) for p in shlex.split(MCP_STDIO_COMMAND)]
        server_params = StdioServerParameters(
            command=cmd_parts[0],
            args=cmd_parts[1:],
            env=os.environ.copy() # Inherit environment variables
        )
        async with stdio_client(server_params) as streams:
            yield streams
    else:
        raise ValueError(f"Unknown mcp_transport in config: {MCP_TRANSPORT}")

async def run_agent():
    # Use our new context manager here
    async with get_mcp_streams() as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            # 1. Fetch Tools & Prepare for Ollama
            mcp_tools = await session.list_tools()
            ollama_tools = []
            for tool in mcp_tools.tools:
                schema = tool.inputSchema.copy()
                ollama_tools.append({
                    'type': 'function',
                    'function': {
                        'name': tool.name,
                        'description': tool.description,
                        'parameters': schema
                    }
                })
            _log_tools(ollama_tools)
            messages = []
            system_prompt = (
                "You are a helpful Site Reliability Engineer (SRE) Agent. "
                "You have access to tools to manage servers. "
                f"Assume the default SSH user is '{DEFAULT_SSH_USER}'. "
                "If the user does not specify a host, ask for it."
            )
            messages.append({'role': 'system', 'content': system_prompt})

            print("\nSRE Agent Ready! (Using Key: " + os.path.basename(DEFAULT_SSH_KEY) + ")")

            while True:
                user_input = input("\nYou: ")
                if user_input.lower() in ["quit", "exit"]:
                    break
                messages.append({'role': 'user', 'content': user_input})

                while True:
                    print("   (Thinking...)")
                    _log_prompt("chat", messages)
                    response = ollama.chat(
                        model=OLLAMA_MODEL,
                        messages=messages,
                        tools=ollama_tools,
                        think=OLLAMA_THINK,
                    )
                    _log_response("chat", response)
                    messages.append(response['message'])

                    if not response['message'].get('tool_calls'):
                        print(f"\nAgent: {response['message'].get('content', '')}")
                        break

                    # B. Handle Tool Calls
                    for tool in response['message']['tool_calls']:
                        func_name = tool['function']['name']
                        args = tool['function']['arguments']                        

                        if 'key_path' not in args or not args['key_path']:
                            args['key_path'] = DEFAULT_SSH_KEY
                        if 'user' not in args or not args['user']:
                            args['user'] = DEFAULT_SSH_USER
                        if args.get('host') in ['localhost', 'self', 'local']:
                            args['host'] = '127.0.0.1'
 
                        print(f"====Calling Tool: {func_name}")
                        print(f"      Host: {args.get('host')} | User: {args.get('user')} | Key: ...{args.get('key_path')[-10:]}")

                        try:
                            result = await session.call_tool(func_name, arguments=args)
                            tool_output = result.content[0].text
                        except Exception as e:
                            tool_output = f"Error: {str(e)}"

                        tool_output = f"[{func_name} host={args.get('host')}] {tool_output}"
                        messages.append({'role': 'tool', 'content': tool_output, 'tool_name': func_name})

if __name__ == "__main__":
    asyncio.run(run_agent())