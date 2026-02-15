# bondage-club-bot-mcp

FastMCP server for Bondage Club bot.

## Deploy with Docker Compose

```bash
cp .env.example .env
# edit .env and chatroom_config.json
docker compose up --build
```

MCP endpoint (Streamable HTTP):
- `http://127.0.0.1:8080/mcp`

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
  - `search_chatrooms`
  - `create_chatroom`
  - `join_chatroom`
  - `leave_chatroom`
  - `get_current_chatroom`
  - `get_chat_history`
  - `query_account`
  - `get_character_data`
  - `get_room_member_detail`
