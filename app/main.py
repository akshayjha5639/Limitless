"""
Limitless — FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.analyze import router as analyze_router
from app.api.routes.questions import router as questions_router
from app.api.routes.generate_pdf import router as pdf_router
from app.api.routes.longitudinal import router as longitudinal_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — validate critical env vars in production
    if settings.APP_ENV == "production":
        settings.validate()
    yield
    # Shutdown (nothing to clean up yet)


app = FastAPI(
    title="Limitless Cognitive Wellness API",
    version="1.0.0",
    description="AI-powered cognitive wellness self-assessment platform.",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Request validation logging
# ---------------------------------------------------------------------------
# uvicorn's access log records only "422 Unprocessable Entity", never which
# field failed, which makes production 422s on /analyze impossible to diagnose
# from the journal. This handler logs the offending fields plus enough request
# context to spot a wrong Content-Type, then returns FastAPI's normal 422 body
# so clients see no behaviour change.
#
# Logs through uvicorn's own logger so the lines land in the same stream and
# format as the access log under `journalctl -u <service>`.
logger = logging.getLogger("uvicorn.error")

MAX_ERRORS_LOGGED = 10
MAX_INPUT_CHARS = 120
MAX_DETAIL_CHARS = 300

# Routing noise from bots and link probes. Logging these would bury the 422s
# this module exists to surface.
UNLOGGED_STATUS_CODES = {404, 405}

# Fields whose value is never written to the log. Everything else is truncated
# or summarised rather than dumped, since request bodies carry assessment
# answers and demographics.
REDACTED_FIELDS = {"name"}


def _summarize_input(value: object) -> str:
    """Render a rejected value compactly, without dumping a whole request body."""
    if isinstance(value, dict):
        keys = ", ".join(sorted(str(k) for k in value)[:15])
        return f"<object keys: {keys}>"
    if isinstance(value, list):
        return f"<list of {len(value)}>"

    rendered = repr(value)
    if len(rendered) > MAX_INPUT_CHARS:
        rendered = rendered[:MAX_INPUT_CHARS] + "...(truncated)"
    return rendered


def _describe_error(err: dict) -> str:
    loc = ".".join(str(part) for part in err.get("loc", ()))
    described = f"{loc or '<body>'}: {err.get('msg', '')}"

    if loc.rsplit(".", 1)[-1] in REDACTED_FIELDS:
        return f"{described} (input=<redacted>)"
    if "input" in err:
        return f"{described} (input={_summarize_input(err['input'])})"
    return described


@app.exception_handler(RequestValidationError)
async def log_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    summary = "; ".join(_describe_error(e) for e in errors[:MAX_ERRORS_LOGGED])
    if len(errors) > MAX_ERRORS_LOGGED:
        summary += f"; ...and {len(errors) - MAX_ERRORS_LOGGED} more"

    logger.warning(
        "422 %s %s | content-type=%s | %d error(s): %s",
        request.method,
        request.url.path,
        request.headers.get("content-type", "<none>"),
        len(errors),
        summary,
    )

    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(errors)},
    )


@app.exception_handler(StarletteHTTPException)
async def log_http_exception(
    request: Request, exc: StarletteHTTPException
) -> Response:
    """
    Log 422s (and other errors) that routes raise deliberately.

    /analyze and /longitudinal-analysis both convert a ValueError from their
    engine into HTTPException(422). Those never become a RequestValidationError,
    so without this they reach the access log as a bare status code with the
    engine's message discarded.
    """
    if exc.status_code >= 400 and exc.status_code not in UNLOGGED_STATUS_CODES:
        detail = str(exc.detail)
        if len(detail) > MAX_DETAIL_CHARS:
            detail = detail[:MAX_DETAIL_CHARS] + "...(truncated)"
        logger.warning(
            "%d %s %s | %s",
            exc.status_code,
            request.method,
            request.url.path,
            detail,
        )

    return await http_exception_handler(request, exc)


API_PREFIX = "/api/v1"

app.include_router(analyze_router,   prefix=API_PREFIX)
app.include_router(questions_router, prefix=API_PREFIX)
app.include_router(pdf_router,       prefix=API_PREFIX)
app.include_router(longitudinal_router, prefix=API_PREFIX)

@app.get("/")
async def root():
    return {"status": "ok"}
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "env": settings.APP_ENV,
    }
