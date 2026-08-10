"""
Limitless — Playground routes (shared by local dev and the deployed demo).

Attaches the browser UI and its small control API to an existing FastAPI app.
Importing this module does NOT import app.main, so callers stay in control of
when application config is first read (config reads env at import time).
"""

import base64
import secrets
from pathlib import Path

from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Flags that may be toggled at runtime from the UI.
BOOL_FLAGS = (
    "ENABLE_CONFIDENCE_INTERVALS",
    "ENABLE_VALIDITY_CHECKS",
    "ENABLE_RELIABLE_CHANGE",
    "ENABLE_METHODOLOGY_PAGE",
)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """HTTP Basic auth over the whole app.

    The playground exposes the full assessment API (and, if a key is
    configured, a billable Gemini call), so a public URL should not be left
    open. /health stays unauthenticated for platform health checks.
    """

    OPEN_PATHS = {"/health"}

    def __init__(self, app, username: str, password: str):
        super().__init__(app)
        self._expected = f"{username}:{password}"

    async def dispatch(self, request, call_next):
        if request.url.path in self.OPEN_PATHS:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
            except Exception:
                decoded = ""
            if secrets.compare_digest(decoded, self._expected):
                return await call_next(request)

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Limitless Playground"'},
        )


def attach_playground(app, html_file: Path):
    """Mount the playground UI + control API onto `app`."""
    from app.core.config import settings

    def _snapshot() -> dict:
        return {
            "SCORING_MODEL_VERSION":       settings.SCORING_MODEL_VERSION,
            "ENABLE_CONFIDENCE_INTERVALS": settings.ENABLE_CONFIDENCE_INTERVALS,
            "ENABLE_VALIDITY_CHECKS":      settings.ENABLE_VALIDITY_CHECKS,
            "ENABLE_RELIABLE_CHANGE":      settings.ENABLE_RELIABLE_CHANGE,
            "ENABLE_METHODOLOGY_PAGE":     settings.ENABLE_METHODOLOGY_PAGE,
            "ITEM_BANK_VERSION":           settings.ITEM_BANK_VERSION,
            "GEMINI_KEY_PRESENT":          bool(settings.GEMINI_API_KEY),
        }

    @app.get("/playground", include_in_schema=False)
    async def playground_ui() -> HTMLResponse:
        # Read per request so editing the HTML only needs a browser refresh
        return HTMLResponse(html_file.read_text(encoding="utf-8"))

    @app.get("/playground/flags", include_in_schema=False)
    async def playground_flags() -> JSONResponse:
        return JSONResponse(_snapshot())

    @app.post("/playground/flags", include_in_schema=False)
    async def set_playground_flags(payload: dict) -> JSONResponse:
        """Flip feature flags at runtime so the demo can switch v1<->v2 live.

        The app reads `settings.<FLAG>` at call time, so mutating the
        singleton takes effect on the next request. This is process-wide
        shared state: fine for a single-audience demo, not something to
        enable on a real multi-tenant deployment.
        """
        version = payload.get("SCORING_MODEL_VERSION")
        if version in ("v1", "v2"):
            settings.SCORING_MODEL_VERSION = version
        for flag in BOOL_FLAGS:
            if flag in payload:
                setattr(settings, flag, bool(payload[flag]))
        return JSONResponse(_snapshot())

    return app
