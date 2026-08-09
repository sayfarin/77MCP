"""Unified Starlette application: web UI + MCP SSE transport."""

from __future__ import annotations

import os
import traceback

from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from . import tools
from .server import mcp
from .api import (
    api_root, api_status as api_status_json, api_list_objects, api_get_object,
    api_get_module, api_get_form, api_search, api_validate_path,
    api_validate_query, api_get_dependencies, api_get_dependents,
    api_export_config, api_export_object, api_reload, cors_options
)

DATA_DIR = os.environ.get("MCP_DATA_DIR", "/data")
MD_FILENAME = "1cv7.md"

_HTML_PAGE_PATH = Path(__file__).parent / "static" / "index.html"
HTML_PAGE = _HTML_PAGE_PATH.read_text(encoding="utf-8")



async def upload_page(request: Request) -> HTMLResponse:
    """Serve the upload page."""
    return HTMLResponse(HTML_PAGE)


async def handle_upload(request: Request) -> JSONResponse:
    """Handle file upload or reload of existing file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    md_path = os.path.join(DATA_DIR, MD_FILENAME)

    form = await request.form()
    uploaded = form.get("file")

    if uploaded is not None and hasattr(uploaded, "read"):
        contents = await uploaded.read()
        if not contents:
            # Empty file in form — try reloading existing
            if not os.path.exists(md_path):
                return JSONResponse({"ok": False, "error": "No file uploaded and no existing file to reload."})
        else:
            with open(md_path, "wb") as f:
                f.write(contents)
    else:
        # No file in request — reload existing
        if not os.path.exists(md_path):
            return JSONResponse({"ok": False, "error": "No file uploaded and no existing file to reload."})

    try:
        tools.init(md_path)
        config = tools.get_loader().config
        return JSONResponse({
            "ok": True,
            "name": config.name,
            "version": config.version,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Parse error: {e}\n{traceback.format_exc()}"})


async def api_status(request: Request) -> JSONResponse:
    """Return current configuration status as JSON."""
    loader = tools.get_loader()
    if not loader.is_loaded:
        return JSONResponse({"loaded": False})

    config = loader.config
    coa_count = 1 if config.chart_of_accounts and config.chart_of_accounts.id else 0
    return JSONResponse({
        "loaded": True,
        "name": config.name,
        "version": config.version,
        "file_path": config.file_path,
        "counts": {
            "constants": len(config.constants),
            "catalogs": len(config.catalogs),
            "documents": len(config.documents),
            "registers": len(config.registers),
            "enums": len(config.enums),
            "reports": len(config.reports),
            "journals": len(config.journals),
            "calc_vars": len(config.calc_vars),
            "chart_of_accounts": coa_count,
        },
    })


async def explorer_page(request: Request) -> HTMLResponse:
    """Serve the interactive Explorer UI."""
    explorer_path = Path(__file__).parent / "static" / "explorer.html"
    if explorer_path.exists():
        return HTMLResponse(explorer_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Explorer not found</h1>", status_code=404)


async def startup() -> None:
    """Try to load existing configuration on startup."""
    os.makedirs(DATA_DIR, exist_ok=True)
    tools.set_data_dir(DATA_DIR)

    candidates = []
    if env_md := os.environ.get("MD_PATH"):
        candidates.append(env_md)
    candidates.extend([
        os.path.join(DATA_DIR, MD_FILENAME),
        os.path.join(DATA_DIR, "1Cv7.MD"),
        "1Cv7.MD",
        "1cv7.md",
    ])

    for candidate in candidates:
        if os.path.exists(candidate) and os.path.isfile(candidate):
            try:
                tools.init(candidate)
                print(f"Auto-loaded configuration from {candidate}")
                break
            except Exception as e:
                print(f"Failed to auto-load {candidate}: {e}")


# Build dual-mode ASGI apps for MCP (SSE + Streamable HTTP)
mcp_sse_app = mcp.sse_app()
mcp_streamable_app = mcp.streamable_http_app()


class MCPDispatchApp:
    """Dispatches HTTP POST requests to Streamable HTTP transport and GET to SSE transport."""

    def __init__(self, sse_app):
        self.sse_app = sse_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "").strip("/")
            method = scope.get("method", "GET")
            sm = getattr(mcp, "_session_manager", None)
            if method == "POST" and path in ("sse", "mcp", ""):
                if sm is not None:
                    await sm.handle_request(scope, receive, send)
                    return
        await self.sse_app(scope, receive, send)







dispatch_app = MCPDispatchApp(mcp_sse_app)



@asynccontextmanager
async def lifespan(app):
    await startup()
    async with mcp_streamable_app.router.lifespan_context(mcp_streamable_app):
        yield


app = Starlette(
    routes=[
        Route("/", upload_page, methods=["GET"]),
        Route("/upload", handle_upload, methods=["POST"]),
        Route("/explorer", explorer_page, methods=["GET"]),
        # REST API routes
        Route("/api", api_root, methods=["GET", "OPTIONS"]),
        Route("/api/status", api_status_json, methods=["GET", "OPTIONS"]),
        Route("/api/objects", api_list_objects, methods=["GET", "OPTIONS"]),
        Route("/api/objects/{type}/{name}", api_get_object, methods=["GET", "OPTIONS"]),
        Route("/api/objects/{type}/{name}/module", api_get_module, methods=["GET", "OPTIONS"]),
        Route("/api/objects/{type}/{name}/form", api_get_form, methods=["GET", "OPTIONS"]),
        Route("/api/objects/{type}/{name}/dependencies", api_get_dependencies, methods=["GET", "OPTIONS"]),
        Route("/api/objects/{type}/{name}/dependents", api_get_dependents, methods=["GET", "OPTIONS"]),
        Route("/api/search", api_search, methods=["GET", "OPTIONS"]),
        Route("/api/validate/path", api_validate_path, methods=["GET", "OPTIONS"]),
        Route("/api/validate/query", api_validate_query, methods=["POST", "OPTIONS"]),
        Route("/api/export", api_export_config, methods=["GET", "OPTIONS"]),
        Route("/api/export/{type}/{name}", api_export_object, methods=["GET", "OPTIONS"]),
        Route("/api/reload", api_reload, methods=["POST", "OPTIONS"]),
        Mount("/", app=dispatch_app),
    ],
    lifespan=lifespan,
)

