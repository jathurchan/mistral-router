"""
Async HTTP client for the Mistral API /v1/chat/completions endpoint.

Uses httpx with connection pooling for optimal performance.
Supports the Mistral chat completions schema (including tools, JSON mode, etc.),
but explicitly disables streaming in this MVP version.
"""

import httpx
import pydantic
import logging
from typing import Dict, Any, Optional

from app.config import settings
from app.api.schemas import ChatCompletionRequest, ChatCompletionResponse

logger = logging.getLogger(__name__)

class MistralAPIError(Exception):
    """Exception raised for Mistral API errors."""
    
    def __init__(
        self,
        status_code: int,
        message: str,
        response_body: Optional[Dict] = None
    ):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"Mistral API Error {status_code}: {message}")

class MistralClient:
    """
    Async HTTP client for the Mistral API.
    """

    def __init__(self):
        """Initialize the Mistral API client."""
        self.base_url = settings.mistral_api_base_url
        self.api_key = settings.mistral_api_key
        self.timeout = settings.router_client_timeout_s

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"{settings.service_name}/1.0.0"
        }
        
        self._client: Optional[httpx.AsyncClient] = None    # lazily initialized

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the persistent httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20
                )
            )
        return self._client

    async def close(self):
        """Close the HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _prepare_request_body(
        self,
        request: ChatCompletionRequest,
        force_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Prepare the request body for the Mistral API.

        - Dumps the Pydantic model to a JSON-ready dict.
        - Overrides the model if 'force_model' is provided.
        - Replaces 'auto' with the default small model if not overridden.
        """
        
        request_dict = request.model_dump(exclude_none=True, mode='json')

        if force_model:
            request_dict["model"] = force_model
        elif request_dict.get("model") == "auto":
            request_dict["model"] = settings.model_small
            
        return request_dict

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        force_model: Optional[str] = None
    ) -> ChatCompletionResponse:
        """
        Send a chat completion request to the Mistral API.

        Args:
            request: The chat completion request schema.
            force_model: The specific model to run (overrides 'auto' or 'model'
                         from the request).

        Returns:
            A validated ChatCompletionResponse object.

        Raises:
            MistralAPIError: For API errors, timeouts, or connection issues.
        """
        client = await self._get_client()
        request_dict = self._prepare_request_body(request, force_model)
        url = f"{self.base_url}/chat/completions"

        logger.debug(
            f"Sending request to Mistral API: model={request_dict.get('model')}, "
            f"messages={len(request_dict.get('messages', []))}, "
            f"tools={len(request_dict.get('tools', [])) > 0}"
        )

        try:
            response = await client.post(
                url,
                json=request_dict,
                headers=self.headers
            )

            if response.status_code != 200:
                error_body = None
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_body = response.json()
                    if isinstance(error_body, dict):
                        error_detail = error_body.get("error", error_body)
                        if isinstance(error_detail, dict):
                            error_msg = error_detail.get("message", error_msg)
                        else:
                            error_msg = str(error_detail)
                except Exception:
                    error_msg = response.text or error_msg

                raise MistralAPIError(
                    status_code=response.status_code,
                    message=error_msg,
                    response_body=error_body
                )

            response_data = response.json()
            
            if "usage" in response_data:
                usage = response_data["usage"]
                logger.debug(
                    f"Mistral usage: {usage.get('prompt_tokens')} prompt, "
                    f"{usage.get('completion_tokens')} completion"
                )

            return ChatCompletionResponse(**response_data)

        except httpx.TimeoutException as e:
            logger.error(f"Timeout calling Mistral API: {e}")
            raise MistralAPIError(
                status_code=504,  # Gateway Timeout
                message="Request to Mistral API timed out"
            )

        except httpx.RequestError as e:
            logger.error(f"Request error calling Mistral API: {e}")
            raise MistralAPIError(
                status_code=503,  # Service Unavailable
                message=f"Failed to connect to Mistral API: {str(e)}"
            )

        except pydantic.ValidationError as e:
            # Mistral returned 200 OK but with a malformed body
            logger.error(f"Failed to validate Mistral API response: {e}")
            raise MistralAPIError(
                status_code=502,  # Bad Gateway
                message=f"Invalid response from Mistral API: {str(e)}",
                response_body={"raw_response": response.text}
            )

        except Exception as e:
            if isinstance(e, MistralAPIError):
                raise  # Re-raise if it's already our error type
            
            logger.error(f"Unexpected error in Mistral client: {e}", exc_info=True)
            raise MistralAPIError(
                status_code=500,  # Internal Server Error
                message=f"Unexpected error: {str(e)}"
            )

    async def health_check(self) -> bool:
        """Check if the Mistral API /models endpoint is reachable."""
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/models",
                headers=self.headers,
                timeout=settings.router_health_check_timeout_s
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Mistral API health check failed: {e}")
            return False