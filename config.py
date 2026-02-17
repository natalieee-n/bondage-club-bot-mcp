import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_SERVER_URL = "https://bondage-club-server.herokuapp.com/"
DEFAULT_ORIGIN = "https://www.bondage-europe.com"
DEFAULT_MCP_TRANSPORT = "http"
DEFAULT_MCP_HOST = "0.0.0.0"
DEFAULT_MCP_PORT = 8080
DEFAULT_MCP_PATH = "/mcp"


@dataclass(frozen=True)
class MCPRuntimeConfig:
    transport: str
    host: str
    port: int
    path: str


def get_bc_credentials() -> tuple[str, str]:
    return os.getenv("BC_USERNAME", ""), os.getenv("BC_PASSWORD", "")


def get_mcp_runtime_config() -> MCPRuntimeConfig:
    transport = os.getenv("MCP_TRANSPORT", DEFAULT_MCP_TRANSPORT).strip().lower()
    if transport in {"streamable-http", "streamable_http"}:
        transport = "http"

    host = os.getenv("MCP_HOST", DEFAULT_MCP_HOST)
    port_raw = os.getenv("MCP_PORT", str(DEFAULT_MCP_PORT))
    path = os.getenv("MCP_PATH", DEFAULT_MCP_PATH)
    if not path.startswith("/"):
        path = f"/{path}"

    try:
        port = int(port_raw)
    except ValueError:
        port = DEFAULT_MCP_PORT

    return MCPRuntimeConfig(transport=transport, host=host, port=port, path=path)
