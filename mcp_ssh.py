#!/usr/bin/env python3
from __future__ import annotations

import socket
import configparser
import uvicorn
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, ContextManager
from contextlib import contextmanager

import paramiko
#from mcp.server.fastmcp import FastMCP
from fastmcp import FastMCP

# Initialize MCP Server
mcp = FastMCP("SRE Collector")

# ---- Configuration Handling ----

def load_config():
    config = configparser.ConfigParser()
    # Default values
    settings = {
        "transport": "streamable-http",
        "host": "127.0.0.1",
        "port": "8000"
    }
    if os.path.exists("config.ini"):
        config.read("config.ini")
        if "server" in config:
            settings.update(dict(config.items("server")))     
    return settings

# ---- SSH helpers ----
@contextmanager
def ssh_session(
    host: str,
    user: str,
    port: int = 22,
    password: Optional[str] = None,
    key_path: Optional[str] = None,
    timeout: int = 10,
    accept_new_hostkey: bool = False,
) -> ContextManager[paramiko.SSHClient]:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy() if accept_new_hostkey else paramiko.RejectPolicy()
    )

    try:
        client.connect(
            hostname=host,
            port=port,
            username=user,
            password=password,
            key_filename=key_path,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
            look_for_keys=True,
            allow_agent=True,
        )
        yield client
    finally:
        client.close()

def _run_cmd(client: paramiko.SSHClient, cmd: str, timeout: int = 20) -> Dict[str, Any]:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return {
        "command": cmd,
        "exit_code": stdout.channel.recv_exit_status(),
        "stdout": stdout.read().decode(errors="replace").strip(),
        "stderr": stderr.read().decode(errors="replace").strip(),
    }

# ---- MCP Tool Boilerplate Helper ----

def run_ssh_command(
    host: str,
    user: str,
    cmd_str: str,
    port: int = 22,
    password: Optional[str] = None,
    key_path: Optional[str] = None,
    timeout: int = 20,
    accept_new_hostkey: bool = False,
    success_exit_codes: tuple = (0,)
) -> Dict[str, Any]:
    """Helper to run an SSH command and capture generalized return payload/errors."""
    collected_at = datetime.now(timezone.utc).isoformat()
    try:
        with ssh_session(
            host, user, port, password, key_path, timeout, accept_new_hostkey
        ) as client:
            result = _run_cmd(client, cmd_str, timeout=timeout)
        return {
            "ok": result["exit_code"] in success_exit_codes,
            "host": host,
            "collected_at_utc": collected_at,
            "data": result,
        }
    except paramiko.AuthenticationException:
        return {"ok": False, "error": "Authentication failed."}
    except Exception as e:
        return {"ok": False, "error": f"Error: {str(e)}"}

# ---- MCP Tools ----

@mcp.tool()
def get_disk_free(
    host: str,
    user: str,
    port: int = 22,
    password: Optional[str] = None,
    key_path: Optional[str] = None,
    timeout: int = 10,
    accept_new_hostkey: bool = False,
) -> Dict[str, Any]:
    """
    Collects disk usage (df -h) from a remote Linux host via SSH.
    """
    return run_ssh_command(host, user, "df -h", port, password, key_path, timeout, accept_new_hostkey)

@mcp.tool()
def get_disk_usage(
    host: str,
    user: str,
    path: str = "/",
    port: int = 22,
    password: Optional[str] = None,
    key_path: Optional[str] = None,
    timeout: int = 20,
    accept_new_hostkey: bool = False,
) -> Dict[str, Any]:
    """
    Collects disk usage for a specific path from a remote Linux host via SSH.
    Returns the top 20 largest files/folders in the specified directory.
    """
    cmd = f"du -sh {path}/* 2>/dev/null | sort -rh | head -n 20"
    result = run_ssh_command(
        host, user, cmd, port, password, key_path, timeout, accept_new_hostkey, 
        success_exit_codes=(0, 1) # du may return 1 on partial permission denied
    )
    if result["ok"]:
        result["path"] = path
    return result

@mcp.tool()
def get_dmesg(
    host: str,
    user: str,
    port: int = 22,
    password: Optional[str] = None,
    key_path: Optional[str] = None,
    timeout: int = 20,
    accept_new_hostkey: bool = False,
) -> Dict[str, Any]:
    """
    Collects dmesg log from a remote Linux host via SSH
    """
    return run_ssh_command(host, user, "dmesg", port, password, key_path, timeout, accept_new_hostkey)
# ---- Main Entry Point ----

if __name__ == "__main__":
    cfg = load_config()
    transport_type = cfg.get("transport", "streamable-http")   
    if transport_type == "streamable-http":
        # Note: FastMCP run args for http might vary by version; 
        # usually it's passed as host/port for the underlying Starlette/Uvicorn app.
        print(f"Starting MCP server on http://{cfg['host']}:{cfg['port']}")
        host = cfg["host"]
        port = int(cfg["port"])
        #official one
        #mcp.run(transport="streamable-http")
        mcp.run(transport="sse", host=host, port=port)
    else:
        # Fallback to standard I/O for CLI/Desktop clients
        mcp.run(transport="stdio")
