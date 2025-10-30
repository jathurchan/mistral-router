"""
Main FastAPI application factory and configuration.

Initializes the application, sets up structured logging,
configures the lifespan (startup/shutdown events), and includes API routers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.api.endpoints import router, set_router_service
from app.services.router_service import RouterService
from app.services.observability import setup_logging
from app.config import settings
from app.__version__ import __version__

setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    logger.info(f"Starting Mistral Router service v{__version__}")
    
    router_service = RouterService()
    set_router_service(router_service)
    
    logger.info("Router service initialized with model thresholds:")
    logger.info(f"  - Length threshold: {settings.router_length_threshold}")
    logger.info(f"  - Token threshold: {settings.router_token_threshold}")
    logger.info(f"  - Conversation threshold: {settings.router_conversation_threshold}")
    
    yield
    
    logger.info("Shutting down Mistral Router service")
    await router_service.close()
    logger.info("Router service closed")

def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI instance
    """
    app = FastAPI(
        title=settings.service_name,
        description=(
            "Intelligent API gateway for Mistral AI that automatically routes "
            "requests to the most cost-effective model while maintaining quality."
        ),
        version=__version__,
        lifespan=lifespan
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(router)
    
    return app

app = create_app()

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": settings.service_name,
        "version": __version__,
        "status": "operational",
        "endpoints": {
            "chat": "/v1/chat/completions",
            "health": "/health",
            "metrics": "/metrics"
        }
    }