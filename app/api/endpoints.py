"""
FastAPI endpoints for the Mistral Router API.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import Response
from typing import Optional
import logging

from app.api.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    HealthResponse,
    ErrorResponse
)
from app.services.router_service import RouterService
from app.services.mistral_client import MistralAPIError
from app.services.observability import (
    get_metrics,
    track_request_metrics,
    router_requests_total
)
from app.config import settings
from app.__version__ import __version__

logger = logging.getLogger(__name__)

router = APIRouter()

# Global RouterService instance (initialized in main.py).
_router_service: Optional[RouterService] = None

def get_router_service() -> RouterService:
    """Dependency to get router service."""
    if _router_service is None:
        logger.critical("Router service is not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Router service not initialized"
        )
    return _router_service

def set_router_service(service: RouterService):
    """Set the global router service instance."""
    global _router_service
    _router_service = service

async def verify_auth(authorization: Optional[str] = Header(None)) -> bool:
    """
    Verify API authentication.
    
    Args:
        authorization: Authorization header
        
    Returns:
        True if authenticated
        
    Raises:
        HTTPException: If authentication fails
    """
    if not authorization:
        logger.warning("Auth error: Missing Authorization header")
        router_requests_total.labels(
            model='unknown', status_code='401', fallback='false'
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )
    
    parts = authorization.split()   # "Bearer <token>"
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Auth error: Invalid Authorization header format")
        router_requests_total.labels(
            model='unknown', status_code='401', fallback='false'
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format"
        )
    
    token = parts[1]
    
    expected_key = settings.router_api_key or settings.mistral_api_key
    
    if token != expected_key:
        logger.warning("Auth error: Invalid API key")
        router_requests_total.labels(
            model='unknown', status_code='401', fallback='false'
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return True

@router.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse}
    }
)
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    authenticated: bool = Depends(verify_auth),
    service: RouterService = Depends(get_router_service)
) -> ChatCompletionResponse:
    """
    Chat completions endpoint - drop-in replacement for Mistral API.
    
    This endpoint intelligently routes requests to the optimal model
    and provides transparent response headers with routing metadata.
    """
    try:
        chat_response, metadata = await service.route_request(request)
        
        track_request_metrics(metadata, status.HTTP_200_OK)

        for key, value in metadata.to_response_headers().items():
            response.headers[key] = value

        return chat_response
    
    except ValueError as e: # (e.g., streaming not supported)
        logger.warning(f"Validation error: {e}")
        router_requests_total.labels(
            model='unknown', status_code='400', fallback='false'
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    except MistralAPIError as e:
        logger.error(f"Mistral API error: {e}")
        router_requests_total.labels(
            model='unknown', status_code=str(e.status_code), fallback='true_or_unknown'
        ).inc()
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message
        )
    
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        router_requests_total.labels(
            model='unknown', status_code='500', fallback='false'
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get(
    "/health",
    response_model=HealthResponse
)
async def health_check(
    service: RouterService = Depends(get_router_service)
) -> HealthResponse:
    """
    Health check endpoint.
    
    Returns service status and basic information.
    Performs a deep check on the upstream Mistral API.
    """
    
    mistral_healthy = await service.mistral_client.health_check()
    
    if not mistral_healthy:
        logger.error("Health check failed: Upstream Mistral API is unreachable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upstream Mistral API health check failed"
        )
    
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=__version__
    )

@router.get("/metrics")
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus exposition format.
    """
    metrics_data = get_metrics()
    return Response(
        content=metrics_data,
        media_type="text/plain; version=0.0.4"
    )