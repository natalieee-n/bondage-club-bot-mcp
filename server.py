import asyncio
import json
import os
from collections import deque
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastmcp import FastMCP

from bondage_club_bot_core import BCBot

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class MCPBCBot(BCBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recent_events: deque[dict] = deque(maxlen=100)

    async def customized_event_handler(self, data):
        self.recent_events.append(data)


class BotRuntime:
    def __init__(self):
        self._bot: MCPBCBot | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def bot(self) -> MCPBCBot | None:
        return self._bot

    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(
        self,
        username: str,
        password: str,
        chatroom_config_path: str,
        appearance_code: str = "",
        server_url: str = "https://bondage-club-server.herokuapp.com/",
        origin: str = "https://www.bondage-europe.com",
    ) -> Dict[str, Any]:
        async with self._lock:
            if self.running() and self._bot:
                return {
                    "ok": True,
                    "message": "bot already running",
                    "member_number": self._bot.player.get("MemberNumber"),
                }

            config_file = Path(chatroom_config_path)
            if not config_file.is_absolute():
                config_file = (BASE_DIR / config_file).resolve()

            with open(config_file, "r", encoding="utf-8") as f:
                room_config = json.load(f)

            self._bot = MCPBCBot(
                username=username,
                password=password,
                chatroom_settings=room_config,
                appearance_code=appearance_code,
                server_url=server_url,
                origin=origin,
            )
            self._task = asyncio.create_task(self._bot.run())

            return {
                "ok": True,
                "message": "bot started",
                "chatroom": room_config.get("Name", ""),
            }

    async def stop(self) -> Dict[str, Any]:
        async with self._lock:
            if not self.running() or self._task is None:
                self._bot = None
                self._task = None
                return {"ok": True, "message": "bot is not running"}

            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

            self._bot = None
            self._task = None
            return {"ok": True, "message": "bot stopped"}

    async def status(self) -> Dict[str, Any]:
        bot = self._bot
        if not bot:
            return {"running": False}

        members = sorted(
            [
                {
                    "member_number": member.get("MemberNumber"),
                    "name": member.get("Name", ""),
                }
                for member in bot.others.values()
            ],
            key=lambda x: x.get("member_number") or 0,
        )

        return {
            "running": self.running(),
            "connected": bot.is_connected,
            "logged_in": bot.is_logged_in,
            "player": {
                "member_number": bot.player.get("MemberNumber"),
                "name": bot.player.get("Name", ""),
            },
            "chatroom": (bot.current_chatroom or {}).get("Name"),
            "member_count": len(members),
            "members": members,
            "recent_event_count": len(bot.recent_events),
        }

    async def send_chat(self, message: str) -> Dict[str, Any]:
        bot = self._bot
        if not bot or not self.running():
            return {"ok": False, "error": "bot is not running"}
        await bot.send_to_chat(message)
        return {"ok": True, "message": "sent"}

    async def recent_events(self, limit: int = 20) -> List[dict]:
        bot = self._bot
        if not bot:
            return []
        safe_limit = max(1, min(limit, 100))
        return list(bot.recent_events)[-safe_limit:]


runtime = BotRuntime()
mcp = FastMCP("bondage-club-bot-mcp")


@mcp.tool()
async def start_bot(
    username: str = "",
    password: str = "",
    chatroom_config_path: str = "chatroom_config.json",
    appearance_code: str = "",
    server_url: str = "https://bondage-club-server.herokuapp.com/",
    origin: str = "https://www.bondage-europe.com",
) -> Dict[str, Any]:
    """Start core bot runtime. Falls back to BC_USERNAME/BC_PASSWORD/APPEARANCE_CODE from env."""
    user = username or os.getenv("BC_USERNAME", "")
    pwd = password or os.getenv("BC_PASSWORD", "")
    appearance = appearance_code or os.getenv("APPEARANCE_CODE", "")
    return await runtime.start(
        username=user,
        password=pwd,
        chatroom_config_path=chatroom_config_path,
        appearance_code=appearance,
        server_url=server_url,
        origin=origin,
    )


@mcp.tool()
async def stop_bot() -> Dict[str, Any]:
    """Stop core bot runtime."""
    return await runtime.stop()


@mcp.tool()
async def get_bot_status() -> Dict[str, Any]:
    """Get connection/login/chatroom/member state."""
    return await runtime.status()


@mcp.tool()
async def send_chat_message(message: str) -> Dict[str, Any]:
    """Send a chat message to current room."""
    return await runtime.send_chat(message)


@mcp.tool()
async def get_recent_events(limit: int = 20) -> List[dict]:
    """Get recent room events received by bot."""
    return await runtime.recent_events(limit=limit)


if __name__ == "__main__":
    mcp.run()
