"""
Limitless — Deployed playground entrypoint (Render / any ASGI host).

Run with:
    uvicorn playground_app:app --host 0.0.0.0 --port $PORT

Everything is configured through environment variables; unlike
dev_playground.py there is no argparse, so this module can be imported
directly by a process manager.

Environment:
    PLAYGROUND_USER / PLAYGROUND_PASSWORD
        When PLAYGROUND_PASSWORD is set, the whole site (except /health)
        requires HTTP Basic auth. Strongly recommended for a public URL.
    SCORING_MODEL_VERSION, ENABLE_* , ITEM_BANK_VERSION
        Initial feature-flag state; also toggleable live from the UI.
    GEMINI_API_KEY
        Optional. Without it, /generate-questions falls back to the static
        question bank, which is usually what you want for a demo.

Note: APP_ENV is deliberately NOT set to "production" here — app.main's
lifespan calls settings.validate() in that mode, which hard-fails startup
when GEMINI_API_KEY is absent.
"""

import os
from pathlib import Path

from starlette.responses import RedirectResponse

from app.main import app
from playground_routes import BasicAuthMiddleware, attach_playground

ROOT = Path(__file__).resolve().parent
HTML_FILE = ROOT / "playground.html"

attach_playground(app, HTML_FILE)

# app.main registers "/" as a JSON health stub and the first matching route
# wins, so it is dropped here (deploy entrypoint only — app/main.py itself is
# untouched) to let the bare URL land on the UI instead of {"status":"ok"}.
app.router.routes = [
    r for r in app.router.routes if getattr(r, "path", None) != "/"
]


@app.get("/", include_in_schema=False)
async def _root_redirect():
    return RedirectResponse("/playground")


# Auth is added last so it wraps every route above.
_password = os.getenv("PLAYGROUND_PASSWORD", "").strip()
if _password:
    app.add_middleware(
        BasicAuthMiddleware,
        username=os.getenv("PLAYGROUND_USER", "limitless").strip(),
        password=_password,
    )
