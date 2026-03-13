import asyncio
import configparser
import json
import ollama
import os
from datetime import datetime
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

def load_config():
    config = configparser.ConfigParser()
    settings = {
        "mcp_server_url": "http://127.0.0.1:4747/sse",
        "ollama_model": "qwen3-coder:30b",
        "default_ssh_user": "root",
        "default_ssh_key": "~/.ssh/id_rsa_private",
        "log_prompts": "false",
        "log_responses": "false",
    }
    if os.path.exists("agent_config.ini"):
        config.read("agent_config.ini")
        if "agent" in config:
            settings.update(dict(config.items("agent")))
    settings["default_ssh_key"] = os.path.expanduser(settings["default_ssh_key"])
    # Parse booleans
    settings["log_prompts"] = settings["log_prompts"].lower() in ("true", "1", "yes")
    settings["log_responses"] = settings["log_responses"].lower() in ("true", "1", "yes")
    return settings

_cfg = load_config()
MCP_SERVER_URL   = _cfg["mcp_server_url"]
OLLAMA_MODEL     = _cfg["ollama_model"]
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

async def run_agent():
    print(f"🔌 Connecting to MCP Server at {MCP_SERVER_URL}...")
    async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            # 1. Fetch Tools & Prepare for Ollama
            mcp_tools = await session.list_tools()
            ollama_tools = []
            # We strip out 'key_path' from the definition we give to Ollama
            # so the model doesn't get confused or hallucinate a path.
            for tool in mcp_tools.tools:
                schema = tool.inputSchema.copy()
                # Optional: You can remove properties you want to hide from the LLM
                # if schema.get('properties', {}).get('key_path'):
                #     del schema['properties']['key_path']
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
            # 2. Set the System Prompt (Context)
            # This tells the model it is an SRE and gives it context about your environment
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
                # Agent loop: allow multiple sequential tool calls
                while True:
                    print("   (Thinking...)")
                    _log_prompt("chat", messages)
                    response = ollama.chat(
                        model=OLLAMA_MODEL,
                        messages=messages,
                        tools=ollama_tools,
                    )
                    _log_response("chat", response)
                    messages.append(response['message'])
                    if not response['message'].get('tool_calls'):
                        # If no tool calls, the agent has responded with text
                        print(f"\nAgent: {response['message'].get('content', '')}")
                        break
                    # B. Handle Tool Calls
                    for tool in response['message']['tool_calls']:
                        func_name = tool['function']['name']
                        args = tool['function']['arguments']                        
                        # --- ARGUMENT INJECTION MAGIC ---
                        # Here we inject the credentials automatically so the LLM doesn't have to.
                        # 1. Inject Key Path if missing
                        if 'key_path' not in args or not args['key_path']:
                            args['key_path'] = DEFAULT_SSH_KEY
                        # 2. Inject User if missing
                        if 'user' not in args or not args['user']:
                            args['user'] = DEFAULT_SSH_USER
                        # 3. Handle "localhost" translation if needed
                        if args.get('host') in ['localhost', 'self', 'local']:
                            args['host'] = '127.0.0.1'
                        print(f"====Calling Tool: {func_name})")
                        print(f"      Host: {args.get('host')} | User: {args.get('user')} | Key: ...{args.get('key_path')[-10:]}")
                        # C. Execute Tool
                        try:
                            # We pass the modified 'args' dictionary here
                            result = await session.call_tool(func_name, arguments=args)
                            tool_output = result.content[0].text
                        except Exception as e:
                            tool_output = f"Error: {str(e)}"
                        messages.append({'role': 'tool', 'content': tool_output})

if __name__ == "__main__":
    asyncio.run(run_agent())