import asyncio
import html
import json
import logging
import mimetypes
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1 import api_router
from app.auth.security import SessionSigner
from app.config import Settings, get_settings, resolve_secret_key
from app.db import init_engine

log = logging.getLogger("plantasaurus")

_INGRESS_PATH_RE = re.compile(r"^/[A-Za-z0-9_\-/]*$")


def base_path_from_request(request: Request) -> str:
    """The URL prefix the app is served under (HA ingress sets X-Ingress-Path)."""
    raw = request.headers.get("X-Ingress-Path", "")
    if not raw or not _INGRESS_PATH_RE.match(raw):
        return "/"
    return raw.rstrip("/") + "/"


def _default_static_dir() -> Path | None:
    for candidate in (Path(__file__).resolve().parents[2] / "frontend" / "dist", Path("/app/static")):
        if (candidate / "index.html").exists():
            return candidate
    return None


def run_migrations(settings: Settings) -> None:
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.db_url)
    command.upgrade(cfg, "head")


def _js_string(value: str) -> str:
    return json.dumps(value).replace("<", "\\u003c")


async def _ha_sync_loop(interval: int) -> None:
    from app.services.homeassistant import run_background_sync

    await asyncio.sleep(min(30, interval))
    while True:
        try:
            await run_in_threadpool(run_background_sync)
        except Exception:  # never let the loop die
            log.exception("Home Assistant sync crashed")
        await asyncio.sleep(interval)


class _McpGate:
    """Front door for `/mcp`.

    Refuses requests while the MCP server is switched off in Settings (checked on every request, so
    turning it off also cuts off connected clients), and serves `/mcp` as well as `/mcp/` because
    clients don't follow redirects on POST.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path == "/mcp" or path.startswith("/mcp/"):
            from app.services.mcp import is_enabled_now

            if not await run_in_threadpool(is_enabled_now):
                response = JSONResponse(
                    {"detail": "The MCP server is turned off. An admin can turn it on in Settings → Integrations."},
                    status_code=503,
                )
                await response(scope, receive, send)
                return
            if path == "/mcp":
                scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)


def _mount_mcp(app: FastAPI):
    from app.mcp_server import Backend, build_server
    from app.mcp_server.auth import ApiTokenVerifier

    # Tools call this same app in-process, passing on the caller's API token.
    mcp = build_server(Backend.in_process(app), auth=ApiTokenVerifier())
    mcp_app = mcp.http_app(path="/")
    app.mount("/mcp", mcp_app, name="mcp")
    app.add_middleware(_McpGate)
    return mcp_app


def create_app(settings: Settings | None = None, *, migrate: bool = True) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    init_engine(settings.db_url)
    if migrate:
        run_migrations(settings)
        from app.services.backup import recover_interrupted

        recover_interrupted()

    mcp_app = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = None
        if settings.ha_sync_interval_seconds > 0:
            task = asyncio.create_task(_ha_sync_loop(settings.ha_sync_interval_seconds))
        try:
            if mcp_app is not None:
                async with mcp_app.lifespan(mcp_app):
                    yield
            else:
                yield
        finally:
            if task:
                task.cancel()

    app = FastAPI(
        lifespan=lifespan,
        title="Plantasaurus",
        version=__version__,
        description=(
            "Track the plants in your house and garden.\n\n"
            "Authenticate with a session cookie (`/api/v1/auth/login`) or an API token "
            "(`Authorization: Bearer pts_…`, created under `/api/v1/tokens`)."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.state.session_signer = SessionSigner(resolve_secret_key(settings), settings.session_max_age_days * 86400)
    app.include_router(api_router)
    if settings.mcp_enabled:
        mcp_app = _mount_mcp(app)

    static_dir = settings.static_dir or _default_static_dir()
    index_template: str | None = None
    if static_dir and (static_dir / "index.html").exists():
        index_template = (static_dir / "index.html").read_text()
        if (static_dir / "assets").exists():
            app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
        for f in static_dir.iterdir():
            if f.is_file() and f.name != "index.html":
                content, mime = f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                app.add_api_route(
                    f"/{f.name}",
                    (lambda c=content, m=mime: Response(c, media_type=m)),
                    include_in_schema=False,
                )
    else:
        log.warning("Frontend build not found; serving API only")

    async def spa_index(request: Request) -> Response:
        if index_template is None:
            return HTMLResponse(
                "<h1>Plantasaurus API</h1><p>Frontend not built. See <a href='api/docs'>API docs</a>.</p>"
            )
        base = base_path_from_request(request)
        inject = f'<base href="{html.escape(base)}"><script>window.__BASE_PATH__={_js_string(base)};</script>'
        body = index_template.replace("<head>", "<head>" + inject, 1)
        return HTMLResponse(body, headers={"Cache-Control": "no-store"})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
        # Unknown non-API GET paths are client-side routes: serve the SPA.
        if exc.status_code == 404 and request.method == "GET" and not request.url.path.startswith("/api/"):
            return await spa_index(request)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    app.add_api_route("/", spa_index, include_in_schema=False)
    return app
