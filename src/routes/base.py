"""Health and identity endpoints."""
from fastapi import APIRouter, Request

base_router = APIRouter(prefix="/api/v1", tags=["base", "api_v1"])


@base_router.get("/health")
async def health(request: Request):
    return {"status": "ok"}


@base_router.get("/")
async def about(request: Request):
    settings = request.app.settings
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "role": settings.AGENT_ROLE,
        "domain": settings.AGENT_DOMAIN,
    }
