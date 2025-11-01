"""
Core routing logic using Strategy Pattern for extensibility.
Implements heuristic-based routing for the MVP.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Set
from enum import Enum

from app.api.schemas import ChatCompletionRequest, Message, SystemMessage, UserMessage
from app.config import settings
from core.models import (
    ModelType,
    RoutingReason,
    RouterDecision,
    TokenEstimator
)

COMPLEXITY_KEYWORDS: Set[str] = {
    "analyze", "analysis", "explain in detail", "compare and contrast",
    "evaluate", "assess", "critique", "argue", "justify", "reason",
    "derive", "prove", "demonstrate", "elaborate", "discuss in depth",
    "comprehensive", "thorough", "detailed explanation", "complex",
    "intricate", "sophisticated", "nuanced", "examine", "investigate",
    "explore", "review", "synthesize", "interpret", "contextualize"
}

class RoutingStrategy(ABC):
    """Abstract base class for routing strategies."""

    @abstractmethod
    def decide(self, request: ChatCompletionRequest) -> RouterDecision:
        """
        Decide which model to route to.

        Args:
            request: The incoming chat completion request

        Returns:
            RouterDecision with model and reasoning
        """
        pass

class HeuristicRoutingStrategy(RoutingStrategy):
    """
    Heuristic-based routing strategy.

    Decision flow:
    1. Manual Override (user explicitly chose 'small' or 'medium')
    2. Capability-Required (tools or JSON mode)
    3. Heuristic Analysis (conversation length, tokens, keywords, prompt length)
    4. Default to small
    """

    def decide(self, request: ChatCompletionRequest) -> RouterDecision:
        """Apply prioritized routing rules."""

        override_decision = self._check_manual_override(request)
        if override_decision:
            return override_decision
        
        capability_decision = self._check_capabilities(request)
        if capability_decision:
            return capability_decision

        estimated_tokens = TokenEstimator.estimate_from_messages(request.messages)
        heuristic_decision = self._check_heuristics(request, estimated_tokens)
        if heuristic_decision:
            return heuristic_decision

        return RouterDecision(
            model=ModelType.SMALL,
            reason=RoutingReason.DEFAULT_SMALL,
            estimated_tokens=estimated_tokens
        )
    
    def _check_manual_override(
        self, request: ChatCompletionRequest
    ) -> Optional[RouterDecision]:
        """
        Rule 1: Check for explicit user model selection.
        """
        requested_model = ModelType.from_string(request.model)
        if not requested_model.is_auto():
            return RouterDecision(
                model=requested_model,
                reason=RoutingReason.MANUAL_OVERRIDE
            )
        return None
    
    def _check_capabilities(
        self, request: ChatCompletionRequest
    ) -> Optional[RouterDecision]:
        """
        Rule 2: Check for features requiring the medium model.
        """
        if request.tools is not None and len(request.tools) > 0:
            return RouterDecision(
                model=ModelType.MEDIUM,
                reason=RoutingReason.FUNCTION_CALLING
            )
        
        if request.response_format == {"type": "json_object"}:
            return RouterDecision(
                model=ModelType.MEDIUM,
                reason=RoutingReason.JSON_MODE
            )
        return None
    
    def _check_heuristics(
        self, request: ChatCompletionRequest, estimated_tokens: int
    ) -> Optional[RouterDecision]:
        """
        Rule 3: Check all heuristics that suggest high complexity.
        """
        if len(request.messages) > settings.router_conversation_threshold:
            return RouterDecision(
                model=ModelType.MEDIUM,
                reason=RoutingReason.HEURISTIC_CONVERSATION,
                estimated_tokens=estimated_tokens
            )

        if estimated_tokens > settings.router_token_threshold:
            return RouterDecision(
                model=ModelType.MEDIUM,
                reason=RoutingReason.HEURISTIC_TOKENS,
                estimated_tokens=estimated_tokens
            )

        if self._contains_complexity_keywords(request.messages):
            return RouterDecision(
                model=ModelType.MEDIUM,
                reason=RoutingReason.HEURISTIC_KEYWORD,
                estimated_tokens=estimated_tokens
            )

        total_length = self._calculate_total_length(request.messages)
        if total_length > settings.router_length_threshold:
            return RouterDecision(
                model=ModelType.MEDIUM,
                reason=RoutingReason.HEURISTIC_LENGTH,
                estimated_tokens=estimated_tokens
            )
        
        return None

    @staticmethod
    def _calculate_total_length(messages: List[Message]) -> int:
        """Calculate total character length of all message content."""
        total_length = 0
        for msg in messages:
            if msg.content:
                total_length += len(msg.content)
        return total_length

    @staticmethod
    def _contains_complexity_keywords(messages: List[Message]) -> bool:
        """Check if user/system messages contain complexity keywords."""
        for message in messages:
            if not isinstance(message, (SystemMessage, UserMessage)):
                continue
            
            if not message.content:
                continue

            content_lower = message.content.lower()
            for keyword in COMPLEXITY_KEYWORDS:
                if keyword in content_lower:
                    return True
        return False

class RoutingStrategyType(str, Enum):
    """Enumeration of available routing strategies."""
    HEURISTIC = "heuristic"

STRATEGY_MAP: dict[RoutingStrategyType, type[RoutingStrategy]] = {
    RoutingStrategyType.HEURISTIC: HeuristicRoutingStrategy,
}

class RouterStrategyFactory:
    """Factory for creating routing strategies."""

    @staticmethod
    def create_strategy(
        strategy_type: RoutingStrategyType = RoutingStrategyType.HEURISTIC
    ) -> RoutingStrategy:
        """
        Create a routing strategy instance.

        Args:
            strategy_type: Type of strategy to create.

        Returns:
            A RoutingStrategy instance.
        """
        implementation_class = STRATEGY_MAP.get(strategy_type)

        if implementation_class:
            return implementation_class()
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        
__all__ = ["RoutingStrategy", "HeuristicRoutingStrategy", "RouterStrategyFactory"]