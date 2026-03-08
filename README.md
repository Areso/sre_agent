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
2. add var/log (cat?)
3. add ps , docker ps
5. a calculator (bc, bc -l)
6. 
```
"Top" Command Quirks 
For get_top, using top -b -n 1 -c is a solid choice to get a single text snapshot. However, be aware that the first iteration of top often shows inaccurate CPU usage percentages (it shows the average since boot, not the current snapshot). A common trick in scripting is to run top -b -n 2 -d 0.5 and only capture the second iteration, though that's harder to parse. Alternatively, running ps aux --sort=-%cpu | head -n 20 is sometimes much more reliable and easier for the LLM to read than the complex visual formatting of top
```
7. re-do to one command ?

using the available tools, check whether the remote server fr1.areso.pro is Okay or not. use "root" user and /Users/areso/.ssh/id_rsa_private key to login to remote
