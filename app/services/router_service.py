"""
Router service that orchestrates routing, fallback, and cost calculation.
"""

import uuid
import logging
from typing import Tuple

from app.config import settings
from core.routing import RouterStrategyFactory, RoutingStrategy, RoutingStrategyType
from core.models import ModelType, RoutingReason, RequestMetadata
from app.api.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.mistral_client import MistralClient, MistralAPIError
from app.services.observability import RequestTimer, request_id_ctx

logger = logging.getLogger(__name__)

class RouterService:
    """
    Core router service that handles request routing, fallback, and cost tracking.
    """

    def __init__(self):
        """Initialize router service with dependencies."""
        self.mistral_client = MistralClient()
        self.routing_strategy: RoutingStrategy = RouterStrategyFactory.create_strategy(
            RoutingStrategyType.HEURISTIC
        )

    async def close(self):
        """Cleanup resources."""
        await self.mistral_client.close()

    async def route_request(
        self,
        request: ChatCompletionRequest
    ) -> Tuple[ChatCompletionResponse, RequestMetadata]:
        """
        Route a chat completion request to the appropriate model.

        Handles:
        - Routing decision based on strategy
        - Automatic fallback on failure
        - Cost calculation
        - Metadata preparation

        Args:
            request: The incoming chat completion request

        Returns:
            Tuple of (response, metadata)
        
        Raises:
            MistralAPIError: If the request fails on the final model (e.g., medium)
                             and no further fallback is possible.
        """
        request_id = str(uuid.uuid4())
        request_id_ctx.set(request_id)

        decision = self.routing_strategy.decide(request)

        logger.info(
            f"Routing decision: model={decision.api_model}, "
            f"reason={decision.reason.value}",
            extra={"routing_decision": decision.to_log_dict()}
        )

        metadata = RequestMetadata(
            request_id=request_id,
            selected_model=decision.model,
            routing_reason=decision.reason,
            fallback_occurred=False
        )

        with RequestTimer() as timer:
            try:
                response = await self._execute_request(request, decision.model)

                if not self._is_valid_response(response):
                    logger.warning(
                        f"Empty response from {decision.model.api_name()}, "
                        f"triggering fallback"
                    )
                    raise MistralAPIError(
                        status_code=502, # Bad Gateway
                        message="Empty or invalid response from upstream model"
                    )

            except MistralAPIError as e:
                if decision.model.is_small():
                    logger.warning(
                        f"Primary model ({decision.model.api_name()}) failed: "
                        f"{e.message}. Attempting fallback to medium.",
                        exc_info=True
                    )

                    metadata.fallback_occurred = True
                    metadata.original_model = decision.model
                    metadata.selected_model = ModelType.MEDIUM
                    metadata.routing_reason = RoutingReason.FALLBACK

                    response = await self._execute_request(request, ModelType.MEDIUM)
                    
                    if not self._is_valid_response(response):
                         logger.error(
                            f"Fallback model {ModelType.MEDIUM.api_name()} "
                            f"also returned an empty response."
                        )
                         raise MistralAPIError(
                            status_code=502,
                            message="Fallback model also returned invalid response"
                        )
                else:
                    logger.error(f"Request failed on final model {decision.model.api_name()}: {e}")
                    metadata.error = str(e)
                    raise

        metadata.latency_ms = timer.elapsed_ms()

        if response.usage:
            metadata.tokens_input = response.usage.prompt_tokens
            metadata.tokens_output = response.usage.completion_tokens
            metadata.cost_usd = self._calculate_cost(
                model=metadata.selected_model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens
            )

        logger.info(
            f"Request completed: {metadata}",
            extra=metadata.to_log_dict()
        )

        return response, metadata

    async def _execute_request(
        self,
        request: ChatCompletionRequest,
        model: ModelType
    ) -> ChatCompletionResponse:
        """
        Execute a request to Mistral API with the specified model.

        Args:
            request: The chat completion request
            model: The logical model to use (small or medium)

        Returns:
            ChatCompletionResponse
        """
        api_model_name = model.api_name()

        logger.debug(f"Executing request with model: {api_model_name}")
        
        return await self.mistral_client.chat_completion(
            request=request,
            force_model=api_model_name
        )

    @staticmethod
    def _is_valid_response(response: ChatCompletionResponse) -> bool:
        """
        Check if a response is valid (not empty).
        A valid response must have at least one choice,
        and that choice must have content (len > 5) or tool calls.
        
        Args:
            response: The response to validate

        Returns:
            True if valid, False otherwise
        """
        if not response.choices or len(response.choices) == 0:
            logger.warning("Invalid response: no 'choices' field")
            return False

        first_choice = response.choices[0]
        if not first_choice.message:
            logger.warning("Invalid response: first choice has no 'message'")
            return False

        message = first_choice.message

        if message.tool_calls:
            return True

        if not message.content:
            logger.warning("Invalid response: message has no 'content' or 'tool_calls'")
            return False
        
        if len(message.content.strip()) < 5:
            logger.warning(
                f"Invalid response: content is too short "
                f"(len={len(message.content.strip())})"
            )
            return False

        return True

    @staticmethod
    def _calculate_cost(
        model: ModelType,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate the cost of a request in USD based on config prices.

        Args:
            model: The *actual* model that was used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        if model.is_small():
            input_price_per_million = settings.price_small_input
            output_price_per_million = settings.price_small_output
        else:  # MEDIUM
            input_price_per_million = settings.price_medium_input
            output_price_per_million = settings.price_medium_output

        input_cost = (input_tokens / 1_000_000) * input_price_per_million
        output_cost = (output_tokens / 1_000_000) * output_price_per_million

        return input_cost + output_cost