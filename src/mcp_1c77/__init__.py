"""MCP server for 1C:Enterprise 7.7 configuration metadata.

Provides LLM clients with access to metadata objects, attributes, modules,
and forms from 1Cv7.MD configuration files.

Features:
- MCP tools for querying metadata (19 tools)
- REST API for HTTP access
- Web UI for file upload and status
- Interactive Explorer UI for browsing
- Python SDK client
- CLI utility
- Dual-transport: SSE + Streamable HTTP (Antigravity, OpenCode, Claude Code)
- Stdio mode for local usage
"""

from .server import mcp
from .web import app

__all__ = ['mcp', 'app']
__version__ = '0.3.0'
