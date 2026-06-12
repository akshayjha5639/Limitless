"""
Limitless — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes.analyze import router as analyze_router
from app.api.routes.questions import router as questions_router
from app.api.routes.generate_pdf import router as pdf_router
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

API_PREFIX = "/api/v1"

app.include_router(analyze_router,   prefix=API_PREFIX)
app.include_router(questions_router, prefix=API_PREFIX)
app.include_router(pdf_router,       prefix=API_PREFIX)

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
