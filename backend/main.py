"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Automated Monitoring and Compliance of Industrial Land Allotments",
    lifespan=lifespan,
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount exports directory for serving generated files
app.mount("/exports", StaticFiles(directory=str(settings.EXPORTS_DIR)), name="exports")

# Import and include routers
from backend.routers import (
    areas,
    auth,
    comparison,
    compliance,
    detection,
    export,
    projects,
)  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(areas.router, prefix="/api/areas", tags=["Areas"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(detection.router, prefix="/api/detect", tags=["Detection"])
app.include_router(comparison.router, prefix="/api/compare", tags=["Comparison"])
app.include_router(compliance.router, prefix="/api/compliance", tags=["Compliance"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
