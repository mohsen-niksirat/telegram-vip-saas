"""Admin dashboard (server-rendered SPA) router."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse, PlainTextResponse

_DASHBOARD_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _DASHBOARD_DIR / "static"
_TEMPLATES_DIR = _DASHBOARD_DIR / "templates"


def get_dashboard_router() -> APIRouter:
    """Router serving the admin dashboard SPA.

    Mounts:
      GET /dashboard                  -> index.html (login + SPA shell)
      GET /dashboard/assets/{file}    -> static assets (style.css, app.js)
    """
    router = APIRouter(tags=["dashboard"], include_in_schema=False)

    @router.get("/dashboard/assets/{file_path:path}", include_in_schema=False)
    async def dashboard_assets(file_path: str) -> Response:
        target = (_STATIC_DIR / file_path).resolve()
        if not str(target).startswith(str(_STATIC_DIR.resolve())) or not target.is_file():
            return PlainTextResponse("Not found", status_code=404)
        return FileResponse(target)

    @router.get("/dashboard")
    async def dashboard_index() -> FileResponse:
        return FileResponse(_TEMPLATES_DIR / "index.html", media_type="text/html")

    return router
