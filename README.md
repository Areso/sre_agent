# Just to try it out
python agent_direct.py \
  --host 127.0.0.1 \
  --user areso \
  --key /Users/areso/.ssh/id_rsa

1.  agent.py fails, if model doesn't support tools. 
2. it doesn't exit anyhow but with Ctrl+C (keyboard interrupt)
3. think about combining agent and agent_direct.cy and may be move some (common) dependecies out
4. expend mcp_ssh.py with new methods

## ideas for mcp
1. add htop (if exists)
2. add var/log
3. add ps , docker ps
4. add systemctl
