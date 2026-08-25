# Sure MCP Server

A Model Context Protocol (MCP) server for integrating with the [Sure](https://github.com/we-promise/sure) self-hosted personal finance platform. This server provides access to your financial accounts, transactions, categories, and AI chat through any MCP-compatible client.

This server speaks **Streamable HTTP** (the standard MCP transport for network-hosted servers), so it can run as a long-lived service — for example in a Docker container on an [Unraid](https://unraid.net/) server — instead of being spawned per-client over stdio.

## Quick Start (Docker / Unraid)

1. **Configure environment variables**. Copy `.env.example` to `.env` and fill in your Sure connection details:

   ```bash
   cp .env.example .env
   ```

   ```env
   SURE_API_URL=http://your-sure-host:3000
   SURE_API_KEY=your-api-key-here
   SURE_VERIFY_SSL=false   # if Sure isn't behind HTTPS
   ```

   `MCP_HOST`, `MCP_PORT`, and `MCP_PATH` control where the server listens (defaults: `0.0.0.0:8000/mcp`) and generally don't need to change.

2. **Build and run**:

   ```bash
   docker compose up -d --build
   ```

   This starts the server listening on `http://<host>:8000/mcp`.

3. **On Unraid specifically**:
   - Easiest: install the **Compose Manager** plugin from Community Applications and point it at this repo's `docker-compose.yml`.
   - Or add the container manually in the Docker tab: image `sure-mcp-server:latest` (build it first with `docker compose build`, or push it to a registry your Unraid box can pull from), container port `8000` mapped to a host port of your choice, and the same environment variables as above.
   - `host.docker.internal` is mapped via `extra_hosts` in the compose file, so `SURE_API_URL=http://host.docker.internal:3000` works if Sure runs directly on the Unraid host. If Sure runs in its own container, use that container's name/IP on the Docker network instead.

4. **Point your MCP client at it**. Any client that supports remote (Streamable HTTP) MCP servers just needs the URL:

   ```json
   {
     "mcpServers": {
       "Sure": {
         "url": "http://your-unraid-ip:8000/mcp"
       }
     }
   }
   ```

   Note that with HTTP hosting, `SURE_API_URL`/`SURE_API_KEY` etc. are configured **once, on the server** (step 1) — not per-client. Every client connecting to this server shares the same Sure backend and credentials.

   For clients that only support locally-spawned (stdio) servers, bridge with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote):

   ```json
   {
     "mcpServers": {
       "Sure": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "http://your-unraid-ip:8000/mcp"]
       }
     }
   }
   ```

### A note on exposure

The server has no built-in authentication of its own — anyone who can reach `http://host:8000/mcp` can use your Sure credentials through it. Keep it on your LAN/VPN, or put it behind a reverse proxy that adds auth (e.g. Authelia, Nginx with basic auth) if you need to reach it from outside your network. Don't port-forward it directly to the internet.

## Alternative: stdio transport (local, single client)

If you'd rather run the server as a local process spawned by a single desktop client instead of hosting it over HTTP, set `MCP_TRANSPORT=stdio` and run it directly:

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

2. **Configure your client** (e.g. Claude Desktop's `claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "Sure": {
         "command": "uv",
         "args": [
           "run",
           "--with", "mcp[cli]",
           "--with-editable", "/path/to/your/sure-mcp-server",
           "mcp", "run",
           "/path/to/your/sure-mcp-server/src/sure_mcp_server/server.py"
         ],
         "env": {
           "SURE_API_URL": "http://localhost:3000",
           "SURE_API_KEY": "your-api-key-here",
           "MCP_TRANSPORT": "stdio"
         }
       }
     }
   }
   ```

### Get Your Sure API Key

1. Start your Sure Docker instance: `docker compose up -d`
2. Log into Sure at `http://localhost:3000`
3. Go to **Settings > API Key** and generate a new key
4. Copy the API key into your `.env` (HTTP hosting) or client config (stdio)

## Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `setup_authentication` | Get setup instructions | None |
| `check_auth_status` | Check authentication status | None |
| `check_connection` | Test API connection | None |
| `get_accounts` | Get all financial accounts | None |
| `get_transactions` | Get transactions with filtering | `limit`, `start_date`, `end_date`, `account_ids`, `category_ids`, `search` |
| `get_transaction` | Get single transaction | `transaction_id` |
| `create_transaction` | Create new transaction | `account_id`, `amount`, `name`, `date`, `category_id`, `notes`, `nature` |
| `update_transaction` | Update transaction | `transaction_id`, `amount`, `name`, `date`, `category_id`, `notes` |
| `delete_transaction` | Delete transaction | `transaction_id` |
| `get_categories` | Get all categories | None |
| `get_category` | Get single category | `category_id` |
| `sync_accounts` | Trigger account sync | None |
| `get_usage` | Get API usage info | None |
| `list_chats` | List AI chat sessions | None |
| `create_chat` | Create new chat | `title` |
| `get_chat` | Get chat details | `chat_id` |
| `send_message` | Send message to AI | `chat_id`, `content` |
| `delete_chat` | Delete chat session | `chat_id` |

## Configuration

### Sure API connection

| Variable | Required | Default | Description |
|----------|----------|---------|--------------|
| `SURE_API_URL` | Yes | - | Base URL of your Sure instance |
| `SURE_API_KEY` | Yes* | - | API key from Sure settings |
| `SURE_ACCESS_TOKEN` | Yes* | - | Alternative to `SURE_API_KEY` (Bearer token) |
| `SURE_TIMEOUT` | No | 30 | Request timeout in seconds |
| `SURE_VERIFY_SSL` | No | true | Verify SSL certificates |

\* One of `SURE_API_KEY` or `SURE_ACCESS_TOKEN` is required.

### MCP server transport

| Variable | Required | Default | Description |
|----------|----------|---------|--------------|
| `MCP_TRANSPORT` | No | `streamable-http` | `streamable-http`, `sse`, or `stdio` |
| `MCP_HOST` | No | `0.0.0.0` | Bind address (HTTP transports only) |
| `MCP_PORT` | No | `8000` | Bind port (HTTP transports only) |
| `MCP_PATH` | No | `/mcp` | HTTP endpoint path (HTTP transports only) |

For local Docker setup, use `SURE_API_URL=http://localhost:3000` and `SURE_VERIFY_SSL=false`.

## Date Formats

- All dates should be in `YYYY-MM-DD` format (e.g., "2024-12-15")
- Transaction amounts: use `nature` field to specify "income" or "expense"

## Troubleshooting

### Connection Issues
1. Verify Sure is running: `docker compose ps`
2. Check the API URL is correct
3. Try `check_connection` tool to diagnose

### Authentication Issues
1. Verify your API key is correct
2. Check the key hasn't expired
3. Regenerate the key in Sure settings

### Server not reachable over HTTP
1. `docker compose logs sure-mcp-server` to confirm it started and check which host/port it bound to
2. Confirm the container port is published (`docker ps`) and reachable from the client machine
3. Make sure the client URL includes the path (default `/mcp`), e.g. `http://host:8000/mcp`

## Project Structure

```
sure-mcp-server/
├── src/sure_mcp_server/
│   ├── __init__.py
│   └── server.py         # Main server implementation
├── pyproject.toml
├── requirements.txt
└── README.md
```

## License

MIT License
