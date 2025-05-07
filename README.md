# MCPTutorial
### Prerequisite

Please clone the repo on local

##### 1. Install python >= 3.10
Select add python to path
![Install Python](MCP/images/installPython.png)

Then restart vscode

##### 2. Install python >= 3.10
run in vscode terminal
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
restart vscode

##### 3. Run python environment
Run below commands inside the MCP folder
```
# Create virtual environment and activate it
uv venv
.venv\Scripts\activate
# if you encounter error like activate.ps1 cannot be      
loaded because running scripts is disabled on this system. For more information, see about_Execution_Policies, run below command
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
# Install dependencies
uv add mcp[cli] httpx Pillow fastmcp openai
# You may need to update to latest MCP version
uv pip install --upgrade fastmcp
```


##### 4. Set up MCP server
Open user setting by ctrl + shift + P

![Install MCP Server](MCP/images/installMCPServer.png)

Paste below to replace
Change the filepath to the local absolute path for the main.py
type open user setting json and paste below
```
{
    "mcp": {
        "servers": {
            "mcpTest": {
                "type": "stdio",
                "command": "uv",
                "args": [
                    "run",
                    "--with",
                    "mcp[cli]",
                    "--with",
                    "pillow",
                    "--with",
                    "fastmcp",
                    "mcp",
                    "run",
                    "C:\\Users\\lipan\\Documents\\GitHub\\MCPTutorial\\MCP\\server.py"
                ]
            }
        }
    }
}
```

##### 4. Run MCP server
click start and it will start running
![Run MCP Server](MCP/images/runMCPServer.png)

sign in github copilot and select claude 3.7

click tool in vscode agent and select tools
![Use MCP Server](MCP/images/useMCPServer.png)


You can ask something like
```
whats the weather in kirkland today
```
![Weather](MCP/images/weather.png)


To debug mcp server
Run below command
```
uv run mcp dev main.py
# if you see the error, npx not found. Please ensure Node.js and npm are properly installed and added to your system PATH.
# then you need to install the latest nodejs https://nodejs.org/en/download
```
![MCP Inspector](MCP/images/mcpInspector.png)
