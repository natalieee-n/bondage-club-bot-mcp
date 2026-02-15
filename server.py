import asyncio
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastmcp import FastMCP

from bondage_club_bot_core import BCBot

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class MCPBCBot(BCBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recent_events: deque[dict] = deque(maxlen=100)
        self.message_history: deque[dict] = deque(maxlen=500)
        self.last_account_query_results: dict[str, Any] = {}
        self.last_chatroom_search_results: list[dict] = []
        self.last_chatroom_create_response: Optional[str] = None

    async def customized_event_handler(self, data):
        self.recent_events.append(data)

    async def on_AccountQueryResult(self, data):
        if isinstance(data, dict) and isinstance(data.get("Query"), str):
            self.last_account_query_results[data["Query"]] = data.get("Result")
        await super().on_AccountQueryResult(data)

    async def on_ChatRoomSearchResult(self, data):
        self.last_chatroom_search_results = [room for room in data if isinstance(room, dict)] if isinstance(data, list) else []
        await super().on_ChatRoomSearchResult(data)

    async def on_ChatRoomCreateResponse(self, data):
        self.last_chatroom_create_response = data if isinstance(data, str) else None
        await super().on_ChatRoomCreateResponse(data)

    async def on_ChatRoomMessage(self, data):
        if isinstance(data, dict):
            msg = dict(data)
            msg["ReceivedAt"] = datetime.now(timezone.utc).isoformat()
            self.message_history.append(msg)
        await super().on_ChatRoomMessage(data)


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

    def _get_running_bot(self) -> MCPBCBot | None:
        bot = self._bot
        if not bot or not self.running():
            return None
        return bot

    async def _ensure_logged_in(self, timeout: float = 15.0) -> tuple[MCPBCBot | None, Dict[str, Any] | None]:
        bot = self._get_running_bot()
        if not bot:
            return None, {"ok": False, "error": "bot is not running"}

        try:
            if hasattr(bot, "ensure_logged_in"):
                ok = await bot.ensure_logged_in(timeout=timeout)
            else:
                if not bot.is_connected:
                    await bot.connect()
                    await asyncio.sleep(0.5)
                if not bot.is_logged_in and not getattr(bot, "_login_requested", False):
                    await bot.login()
                elapsed = 0.0
                interval = 0.2
                ok = bot.is_logged_in
                while not ok and elapsed < timeout:
                    await asyncio.sleep(interval)
                    elapsed += interval
                    ok = bot.is_logged_in
        except Exception as exc:
            return None, {"ok": False, "error": f"login error: {exc}"}

        if not ok:
            return None, {"ok": False, "error": "login failed or timeout"}
        return bot, None

    async def start(
        self,
        username: str,
        password: str,
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

            self._bot = MCPBCBot(
                username=username,
                password=password,
                appearance_code=appearance_code,
                server_url=server_url,
                origin=origin,
            )
            self._task = asyncio.create_task(self._bot.run())

            return {
                "ok": True,
                "message": "bot started",
            }

    async def login(self, username: str = "", password: str = "", timeout: float = 15.0) -> Dict[str, Any]:
        bot = self._get_running_bot()
        if not bot:
            return {"ok": False, "error": "bot is not running"}

        if username:
            bot.username = username
        if password:
            bot.password = password

        if not bot.username:
            bot.username = os.getenv("BC_USERNAME", "")
        if not bot.password:
            bot.password = os.getenv("BC_PASSWORD", "")

        if not bot.username or not bot.password:
            return {"ok": False, "error": "username/password is empty"}

        if not bot.is_connected:
            connected = await bot.connect()
            if not connected:
                return {"ok": False, "error": "connect failed"}

        await bot.login()
        if hasattr(bot, "wait_for_login"):
            ok = await bot.wait_for_login(timeout=timeout)
        else:
            elapsed = 0.0
            interval = 0.2
            ok = bot.is_logged_in
            while not ok and elapsed < timeout:
                await asyncio.sleep(interval)
                elapsed += interval
                ok = bot.is_logged_in

        if not ok:
            return {"ok": False, "error": "login failed or timeout"}

        return {
            "ok": True,
            "member_number": bot.player.get("MemberNumber"),
            "name": bot.player.get("Name", ""),
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
        bot, err = await self._ensure_logged_in(timeout=15.0)
        if err:
            return err
        if not bot:
            return {"ok": False, "error": "bot is not running"}
        await bot.send_to_chat(message)
        return {"ok": True, "message": "sent"}

    async def recent_events(self, limit: int = 20) -> List[dict]:
        bot = self._bot
        if not bot:
            return []
        safe_limit = max(1, min(limit, 100))
        return list(bot.recent_events)[-safe_limit:]

    async def search_rooms(
        self,
        query: str = "",
        language: str = "",
        space: str = "",
        game: str = "",
        full_rooms: bool = True,
        show_locked: bool = True,
        search_descs: bool = False,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        bot, err = await self._ensure_logged_in(timeout=15.0)
        if err:
            return err
        if not bot:
            return {"ok": False, "error": "bot is not running"}

        kwargs = {
            "Language": language,
            "Space": space,
            "Game": game,
            "FullRooms": full_rooms,
            "ShowLocked": show_locked,
            "SearchDescs": search_descs,
        }
        if hasattr(bot, "search_chatrooms"):
            rooms = await bot.search_chatrooms(query=query, timeout=timeout, **kwargs)
        else:
            bot.last_chatroom_search_results = []
            await bot.search_chatroom(query, **kwargs)
            elapsed = 0.0
            interval = 0.2
            while elapsed < timeout:
                if getattr(bot, "_chatroom_search_done", False):
                    break
                await asyncio.sleep(interval)
                elapsed += interval
            rooms = bot.last_chatroom_search_results

        return {"ok": True, "count": len(rooms), "rooms": rooms}

    async def create_room(
        self,
        name: str,
        description: str,
        background: str,
        limit: int = 10,
        language: str = "EN",
        space: str = "",
        game: str = "",
        private: bool = False,
        locked: bool = False,
        block_category: list[str] | None = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        bot, err = await self._ensure_logged_in(timeout=15.0)
        if err:
            return err
        if not bot:
            return {"ok": False, "error": "bot is not running"}

        settings: Dict[str, Any] = {
            "Name": name,
            "Description": description,
            "Background": background,
            "Limit": limit,
            "Language": language,
            "Space": space,
            "Game": game,
            "Private": private,
            "Locked": locked,
            "BlockCategory": block_category or [],
            "Ban": [],
            "Admin": [bot.player.get("MemberNumber")] if isinstance(bot.player.get("MemberNumber"), int) else [],
            "Whitelist": [],
        }

        if hasattr(bot, "create_chatroom_and_wait"):
            result = await bot.create_chatroom_and_wait(settings, timeout=timeout)
        else:
            bot.last_chatroom_create_response = None
            await bot.create_chatroom(settings)
            elapsed = 0.0
            interval = 0.2
            result = bot.last_chatroom_create_response
            while elapsed < timeout and result is None:
                await asyncio.sleep(interval)
                elapsed += interval
                result = bot.last_chatroom_create_response

        return {
            "ok": result == "ChatRoomCreated",
            "response": result,
            "current_chatroom": (bot.current_chatroom or {}).get("Name"),
        }

    async def join_room(self, name: str, timeout: float = 10.0) -> Dict[str, Any]:
        bot, err = await self._ensure_logged_in(timeout=15.0)
        if err:
            return err
        if not bot:
            return {"ok": False, "error": "bot is not running"}

        if hasattr(bot, "join_chatroom_and_wait"):
            response = await bot.join_chatroom_and_wait(name, timeout=timeout)
        else:
            await bot.join_chatroom(name)
            elapsed = 0.0
            interval = 0.2
            response = getattr(bot, "_chatroom_join_response", None)
            while elapsed < timeout and response is None:
                await asyncio.sleep(interval)
                elapsed += interval
                response = getattr(bot, "_chatroom_join_response", None)

        return {
            "ok": response == "JoinedRoom",
            "response": response,
            "current_chatroom": (bot.current_chatroom or {}).get("Name"),
        }

    async def leave_room(self, timeout: float = 5.0) -> Dict[str, Any]:
        bot = self._get_running_bot()
        if not bot:
            return {"ok": False, "error": "bot is not running"}

        current_name = (bot.current_chatroom or {}).get("Name")
        if not current_name:
            return {"ok": True, "message": "already not in chatroom"}

        if hasattr(bot, "leave_chatroom"):
            await bot.leave_chatroom()
        else:
            await bot.event_queue.put_event("ChatRoomLeave", {})

        elapsed = 0.0
        interval = 0.2
        while elapsed < timeout:
            if not bot.current_chatroom:
                return {"ok": True, "message": "left chatroom"}
            await asyncio.sleep(interval)
            elapsed += interval

        return {
            "ok": False,
            "error": "leave timeout",
            "current_chatroom": (bot.current_chatroom or {}).get("Name"),
        }

    async def get_chat_history(self, limit: int = 20) -> Dict[str, Any]:
        bot = self._get_running_bot()
        if not bot:
            return {"ok": False, "error": "bot is not running"}

        safe_limit = max(1, min(limit, 500))
        if hasattr(bot, "get_chat_history"):
            messages = bot.get_chat_history(limit=safe_limit)
        else:
            messages = list(bot.message_history)[-safe_limit:]
        return {"ok": True, "count": len(messages), "messages": messages}

    async def account_query(self, query: str, timeout: float = 10.0) -> Dict[str, Any]:
        bot, err = await self._ensure_logged_in(timeout=15.0)
        if err:
            return err
        if not bot:
            return {"ok": False, "error": "bot is not running"}

        if hasattr(bot, "query_account"):
            result = await bot.query_account(query=query, timeout=timeout)
        else:
            bot.last_account_query_results.pop(query, None)
            await bot.event_queue.put_event("AccountQuery", {"Query": query})
            elapsed = 0.0
            interval = 0.2
            while elapsed < timeout:
                if query in bot.last_account_query_results:
                    break
                await asyncio.sleep(interval)
                elapsed += interval
            result = bot.last_account_query_results.get(query)

        return {"ok": result is not None, "query": query, "result": result}

    async def get_character_data(self, member_number: int = 0) -> Dict[str, Any]:
        bot = self._get_running_bot()
        if not bot:
            return {"ok": False, "error": "bot is not running"}

        if member_number > 0:
            if hasattr(bot, "get_character_data"):
                character = bot.get_character_data(member_number=member_number)
            else:
                if bot.player.get("MemberNumber") == member_number:
                    character = bot.player
                else:
                    character = bot.others.get(member_number)
            return {"ok": character is not None, "character": character}

        if hasattr(bot, "get_character_data"):
            characters = bot.get_character_data()
        else:
            characters = dict(bot.others)
            self_no = bot.player.get("MemberNumber")
            if isinstance(self_no, int):
                characters[self_no] = bot.player

        return {"ok": True, "count": len(characters), "characters": characters}

    async def get_room_member_detail(self, member_number: int) -> Dict[str, Any]:
        bot = self._get_running_bot()
        if not bot:
            return {"ok": False, "error": "bot is not running"}
        if member_number <= 0:
            return {"ok": False, "error": "member_number must be > 0"}

        if hasattr(bot, "get_character_data"):
            character = bot.get_character_data(member_number=member_number)
        else:
            if bot.player.get("MemberNumber") == member_number:
                character = bot.player
            else:
                character = bot.others.get(member_number)

        if not character:
            return {
                "ok": False,
                "error": "member not found in local cache",
                "chatroom": (bot.current_chatroom or {}).get("Name"),
            }

        room = bot.current_chatroom or {}
        player_order = room.get("PlayerOrder") if isinstance(room.get("PlayerOrder"), list) else []
        return {
            "ok": True,
            "chatroom": room.get("Name"),
            "member_number": member_number,
            "is_self": bot.player.get("MemberNumber") == member_number,
            "is_in_player_order": member_number in player_order,
            "character": character,
        }

    async def get_current_room(self) -> Dict[str, Any]:
        bot = self._get_running_bot()
        if not bot:
            return {"ok": False, "error": "bot is not running"}
        return {"ok": True, "chatroom": bot.current_chatroom}


runtime = BotRuntime()
mcp = FastMCP("bondage-club-bot-mcp")


@mcp.tool()
async def start_bot(
    username: str = "",
    password: str = "",
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


@mcp.tool()
async def search_chatrooms(
    query: str = "",
    language: str = "",
    space: str = "",
    game: str = "",
    full_rooms: bool = True,
    show_locked: bool = True,
    search_descs: bool = False,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Search chatrooms by query and filters."""
    return await runtime.search_rooms(
        query=query,
        language=language,
        space=space,
        game=game,
        full_rooms=full_rooms,
        show_locked=show_locked,
        search_descs=search_descs,
        timeout=timeout,
    )


@mcp.tool()
async def create_chatroom(
    name: str,
    description: str,
    background: str,
    limit: int = 10,
    language: str = "EN",
    space: str = "",
    game: str = "",
    private: bool = False,
    locked: bool = False,
    block_category: list[str] | None = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Create a chatroom with explicit room settings."""
    return await runtime.create_room(
        name=name,
        description=description,
        background=background,
        limit=limit,
        language=language,
        space=space,
        game=game,
        private=private,
        locked=locked,
        block_category=block_category,
        timeout=timeout,
    )


@mcp.tool()
async def join_chatroom(name: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Join an existing chatroom by exact room name."""
    return await runtime.join_room(name=name, timeout=timeout)


@mcp.tool()
async def leave_chatroom(timeout: float = 5.0) -> Dict[str, Any]:
    """Leave current chatroom."""
    return await runtime.leave_room(timeout=timeout)


@mcp.tool()
async def get_current_chatroom() -> Dict[str, Any]:
    """Get full current chatroom snapshot if bot is in a room."""
    return await runtime.get_current_room()


@mcp.tool()
async def get_chat_history(limit: int = 20) -> Dict[str, Any]:
    """Read recent chat messages received by bot."""
    return await runtime.get_chat_history(limit=limit)


@mcp.tool()
async def query_account(query: str = "OnlineFriends", timeout: float = 10.0) -> Dict[str, Any]:
    """Run AccountQuery (e.g. OnlineFriends, EmailStatus)."""
    return await runtime.account_query(query=query, timeout=timeout)


@mcp.tool()
async def get_character_data(member_number: int = 0) -> Dict[str, Any]:
    """Get character data by member number, or all cached characters when 0."""
    return await runtime.get_character_data(member_number=member_number)


@mcp.tool()
async def get_room_member_detail(member_number: int) -> Dict[str, Any]:
    """Get detailed data for a specific room member from synchronized character cache."""
    return await runtime.get_room_member_detail(member_number=member_number)


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "http").strip().lower()
    if transport in {"streamable-http", "streamable_http"}:
        transport = "http"

    if transport == "http":
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8080"))
        path = os.getenv("MCP_PATH", "/mcp")
        if not path.startswith("/"):
            path = f"/{path}"
        mcp.run(transport="http", host=host, port=port, path=path)
    else:
        mcp.run(transport=transport)
