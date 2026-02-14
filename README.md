# bondage-club-bot-mcp

FastMCP server for Bondage Club bot.

## Deploy with Docker Compose

```bash
cp .env.example .env
# edit .env and chatroom_config.json
docker compose up --build
```

## Notes

- This project is deployment-oriented and not packaged as a library.
- `bondage-club-bot-core` is installed from GitHub in Docker build:
  `https://github.com/natalieee-n/bondage-club-bot-core`.
- MCP tools provided by `server.py`:
  - `start_bot`
  - `stop_bot`
  - `get_bot_status`
  - `send_chat_message`
  - `get_recent_events`
