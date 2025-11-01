"""
Routing domain models for Mistral /v1/chat/completions.

Includes:
- ModelType — supported models
- RoutingReasonCategory — decision categories
- RoutingReason — specific reasons
- GenerationParams — generation controls
- RouterDecision — validated routing result
- RequestMetadata — lifecycle tracking
- Helpers — token estimation, logging/metrics adapters

Principles:
- Immutable enums
- Pydantic v2 with validation & computed fields
- Behavior-rich models
- Self-documenting and testable
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field, field_validator

from app.config import settings
from app.api.schemas import Message

class ModelType(str, Enum):
    """Logical model labels."""

    SMALL = "small"
    MEDIUM = "medium"
    AUTO = "auto"

    def is_small(self) -> bool:
        """Whether this is the small model."""
        return self == ModelType.SMALL

    def is_medium(self) -> bool:
        """Whether this is the medium model."""
        return self == ModelType.MEDIUM

    def is_auto(self) -> bool:
        """Whether this is the virtual routing signal."""
        return self == ModelType.AUTO

    def is_billable(self) -> bool:
        """Whether the model incurs cost (AUTO is virtual)."""
        return self in (ModelType.SMALL, ModelType.MEDIUM)

    def supports_tools(self) -> bool:
        """Whether tool/function calling is supported."""
        return self == ModelType.MEDIUM

    def supports_json_mode(self) -> bool:
        """Whether JSON mode is supported."""
        return self.is_billable()

    def get_display_name(self) -> str:
        """Human-readable name."""
        return {
            ModelType.SMALL: "Mistral Small (Cost-Optimized)",
            ModelType.MEDIUM: "Mistral Medium (High-Capability)",
            ModelType.AUTO: "Auto-Routing (Intelligent Selection)",
        }.get(self, self.value)
    
    def api_name(self) -> str:
        """Get the actual API model name from settings."""
        if self.is_small():
            return settings.model_small
        if self.is_medium():
            return settings.model_medium
        return "unknown"

    def get_relative_cost(self) -> float:
        """Relative cost multiplier (small = 1.0)."""
        if self == ModelType.SMALL:
            return 1.0
        if self == ModelType.MEDIUM:
            return (
                settings.price_medium_input + settings.price_medium_output
            ) / (settings.price_small_input + settings.price_small_output)
        if self == ModelType.AUTO:
            return 0.0
        return 1.0

    @classmethod
    def from_string(cls, model: str) -> ModelType:
        """Parse string to ModelType (accepts logical labels and configured IDs)."""
        m = (model or "").strip().lower()

        mapping = {
            cls.SMALL.value: cls.SMALL,
            cls.MEDIUM.value: cls.MEDIUM,
            cls.AUTO.value: cls.AUTO,
            settings.model_small.lower(): cls.SMALL,
            settings.model_medium.lower(): cls.MEDIUM,
        }

        if m in mapping:
            return mapping[m]
        
        if "auto" in m:
            return cls.AUTO
        if "small" in m:
            return cls.SMALL
        if "medium" in m:
            return cls.MEDIUM
        
        return cls.AUTO

    @classmethod
    def is_valid_api_model(cls, model: str) -> bool:
        """Whether the string maps to a billable model."""
        if not model:
            return False
        m = model.strip().lower()
        return m in {settings.model_small.lower(), settings.model_medium.lower()}


class RoutingReasonCategory(str, Enum):
    """Routing categories."""
    
    USER_CONTROLLED = "user_controlled"         # Manual override
    CAPABILITY_REQUIRED = "capability_required" # Function calling, JSON mode
    HEURISTIC = "heuristic"                     # Length, tokens, keywords
    FALLBACK = "fallback"                       # Error recovery
    DEFAULT = "default"                         # Catch-all


class RoutingReason(str, Enum):
    """Routing reasons."""

    # User
    MANUAL_OVERRIDE = "manual_override"

    # Capabilities
    FUNCTION_CALLING = "function_calling"
    JSON_MODE = "json_mode"

    # Heuristics
    HEURISTIC_CONVERSATION = "heuristic_conversation"
    HEURISTIC_TOKENS = "heuristic_tokens"
    HEURISTIC_KEYWORD = "heuristic_keyword"
    HEURISTIC_LENGTH = "heuristic_length"

    # Defaults
    DEFAULT_SMALL = "default_small"
    FALLBACK = "fallback"

    def get_category(self) -> RoutingReasonCategory:
        mapping = {
            self.MANUAL_OVERRIDE: RoutingReasonCategory.USER_CONTROLLED,
            self.FUNCTION_CALLING: RoutingReasonCategory.CAPABILITY_REQUIRED,
            self.JSON_MODE: RoutingReasonCategory.CAPABILITY_REQUIRED,
            self.HEURISTIC_CONVERSATION: RoutingReasonCategory.HEURISTIC,
            self.HEURISTIC_TOKENS: RoutingReasonCategory.HEURISTIC,
            self.HEURISTIC_KEYWORD: RoutingReasonCategory.HEURISTIC,
            self.HEURISTIC_LENGTH: RoutingReasonCategory.HEURISTIC,
            self.DEFAULT_SMALL: RoutingReasonCategory.DEFAULT,
            self.FALLBACK: RoutingReasonCategory.FALLBACK,
        }
        return mapping.get(self, RoutingReasonCategory.DEFAULT)

    def get_display_name(self) -> str:
        return {
            self.MANUAL_OVERRIDE: "User override",
            self.FUNCTION_CALLING: "Tool calling required",
            self.JSON_MODE: "JSON mode required",
            self.HEURISTIC_CONVERSATION: "Long conversation",
            self.HEURISTIC_TOKENS: "High token estimate",
            self.HEURISTIC_KEYWORD: "Complex keywords",
            self.HEURISTIC_LENGTH: "Prompt too long",
            self.DEFAULT_SMALL: "Default to small",
            self.FALLBACK: "Fallback triggered",
        }.get(self, self.value)

    def is_user_override(self) -> bool:
        return self.get_category() == RoutingReasonCategory.USER_CONTROLLED

    def is_capability_driven(self) -> bool:
        return self.get_category() == RoutingReasonCategory.CAPABILITY_REQUIRED

    def is_heuristic(self) -> bool:
        return self.get_category() == RoutingReasonCategory.HEURISTIC


class GenerationParams(BaseModel):
    """Generation parameters for Mistral API requests."""

    temperature: float = Field(
        default=0.7,
        description="Sampling temperature for generation"
        )
    top_p: float = Field(
        default=1.0,
        description="Nucleus sampling parameter"
        )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum tokens to generate"
        )
    random_seed: Optional[int] = Field(
        default=None,
        description="Random seed for reproducibility"
        )
    safe_prompt: bool = Field(
        default=False,
        description="Enable Mistral safety prompt injection"
        )

    def to_dict(self) -> Dict[str, Any]:
        """API payload dict (excludes None)."""
        return self.model_dump(exclude_none=True)

    @computed_field
    @property
    def is_deterministic(self) -> bool:
        return self.temperature == 0.0 and self.random_seed is not None

    @computed_field
    @property
    def is_creative(self) -> bool:
        return self.temperature > 1.
    

class RouterDecision(BaseModel):
    """Result of a routing strategy decision."""

    model: ModelType
    reason: RoutingReason
    estimated_tokens: Optional[int] = Field(
        default=None,
        ge=0
        )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0
        )
    metadata: Dict[str, Any] = Field(
        default_factory=dict
        )

    class Config:
        frozen = True   # Immutable

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: ModelType) -> ModelType:
        if v == ModelType.AUTO:
            raise ValueError("AUTO cannot be final routing decision")
        return v

    @computed_field
    @property
    def category(self) -> RoutingReasonCategory:
        return self.reason.get_category()

    @computed_field
    @property
    def is_override(self) -> bool:
        return self.reason.is_user_override()

    @computed_field
    @property
    def is_capability_driven(self) -> bool:
        return self.reason.is_capability_driven()

    @computed_field
    @property
    def api_model(self) -> str:
        """Configured API model ID for this decision."""
        return self.model.api_name()

    def to_log_dict(self) -> Dict[str, Any]:
        """Structured log with logical and actual model."""
        return {
            "model_logical": self.model.value,
            "model_actual": self.api_model,
            "reason": self.reason.value,
            "category": self.category.value,
            "estimated_tokens": self.estimated_tokens,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    def __str__(self) -> str:
        tokens = f", ~{self.estimated_tokens} tokens" if self.estimated_tokens else ""
        return f"RouterDecision(model={self.model.value} -> {self.api_model}, reason={self.reason.value}{tokens})"


class RequestMetadata(BaseModel):
    """
    Complete lifecycle metadata for a routed request.

    Tracks everything from routing decision through execution to final response,
    including costs, timing, and fallback information.
    """

    request_id: str = Field(description="Unique request identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Request timestamp"
    )

    selected_model: ModelType = Field(description="Final executed model")
    routing_reason: RoutingReason = Field(description="Routing decision reason")
    original_model: Optional[ModelType] = Field(
        default=None,
        description="Original model before fallback"
    )
    fallback_occurred: bool = Field(default=False, description="Whether fallback happened")

    latency_ms: Optional[float] = Field(default=None, ge=0.0, description="Request latency")

    tokens_input: Optional[int] = Field(default=None, ge=0, description="Input tokens")
    tokens_output: Optional[int] = Field(default=None, ge=0, description="Output tokens")
    
    cost_usd: Optional[float] = Field(default=None, ge=0.0, description="Request cost in USD")

    generation_params: Optional[GenerationParams] = Field(
        default=None,
        description="Generation parameters used"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")

    @computed_field
    @property
    def total_tokens(self) -> Optional[int]:
        if self.tokens_input is not None and self.tokens_output is not None:
            return self.tokens_input + self.tokens_output
        return None

    @computed_field
    @property
    def cost_per_token(self) -> Optional[float]:
        if self.cost_usd and self.total_tokens and self.total_tokens > 0:
            return self.cost_usd / self.total_tokens
        return None

    @computed_field
    @property
    def tokens_per_second(self) -> Optional[float]:
        if self.total_tokens and self.latency_ms and self.latency_ms > 0:
            return (self.total_tokens * 1000.0) / self.latency_ms
        return None

    @computed_field
    @property
    def is_successful(self) -> bool:
        return self.error is None

    @computed_field
    @property
    def category(self) -> RoutingReasonCategory:
        return self.routing_reason.get_category()

    @computed_field
    @property
    def selected_model_actual(self) -> str:
        """Configured API model ID for the selected logical model."""
        model_str = str(self.selected_model)
        return ModelType.from_string(model_str).api_name()

    @computed_field
    @property
    def original_model_actual(self) -> Optional[str]:
        if self.original_model is None:
            return None
        model_str = str(self.original_model)
        return ModelType.from_string(model_str).api_name()

    def to_response_headers(self) -> Dict[str, str]:
        """HTTP response headers (actual + logical)."""
        headers = {
            "X-Router-Model": self.selected_model_actual,
            "X-Router-Model-Logical": str(self.selected_model),
            "X-Router-Reason": self.routing_reason.value,
            "X-Router-Fallback": str(self.fallback_occurred).lower(),
            "X-Router-Request-ID": self.request_id,
        }

        if self.latency_ms is not None:
            headers["X-Router-Latency-MS"] = f"{self.latency_ms:.2f}"

        if self.cost_usd is not None:
            headers["X-Router-Cost-USD"] = f"{self.cost_usd:.8f}"

        if self.tokens_input is not None:
            headers["X-Router-Tokens-Input"] = str(self.tokens_input)

        if self.tokens_output is not None:
            headers["X-Router-Tokens-Output"] = str(self.tokens_output)

        if self.original_model is not None:
            headers["X-Router-Original-Model"] = self.original_model_actual or ""
            headers["X-Router-Original-Model-Logical"] = str(self.original_model)

        return headers

    def to_log_dict(self) -> Dict[str, Any]:
        """Structured log (actual + logical)."""
        data = {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "model_logical": str(self.selected_model),
            "model_actual": self.selected_model_actual,
            "reason": self.routing_reason.value,
            "category": self.category.value,
            "fallback": self.fallback_occurred,
            "success": self.is_successful,
        }

        if self.latency_ms is not None:
            data["latency_ms"] = round(self.latency_ms, 2)

        if self.cost_usd is not None:
            data["cost_usd"] = round(self.cost_usd, 8)

        if self.tokens_input is not None:
            data["tokens_input"] = self.tokens_input

        if self.tokens_output is not None:
            data["tokens_output"] = self.tokens_output

        if self.total_tokens is not None:
            data["tokens_total"] = self.total_tokens

        if self.original_model is not None:
            data["original_model_logical"] = str(self.original_model)
            data["original_model_actual"] = self.original_model_actual

        if self.error:
            data["error"] = self.error

        return data

    def to_metrics_labels(self) -> Dict[str, str]:
        """Prometheus labels (logical for cardinality control)."""
        return {
            "model": str(self.selected_model),
            "reason": self.routing_reason.value,
            "category": self.category.value,
            "fallback": str(self.fallback_occurred).lower(),
            "success": str(self.is_successful).lower(),
        }

    def __str__(self) -> str:
        status = "✓" if self.is_successful else "✗"
        fb = " (fallback)" if self.fallback_occurred else ""
        cost = f", ${self.cost_usd:.6f}" if self.cost_usd else ""
        latency = f", {self.latency_ms:.0f}ms" if self.latency_ms else ""

        return f"{status} {self.selected_model} -> {self.selected_model_actual}{fb} ({self.routing_reason.value}{cost}{latency})"
    

class TokenEstimator:
    """Heuristic token estimator (~4 chars/token)."""

    CHARS_PER_TOKEN = 4.0   # standard heuristic

    @classmethod
    def estimate_from_text(cls, text: str) -> int:
        if not text:
            return 0
        return max(1, int(len(text) / cls.CHARS_PER_TOKEN))

    @classmethod
    def estimate_from_messages(cls, messages: List[Message]) -> int:
        total_chars = 0
        for msg in messages:
            if msg.content:
                total_chars += len(msg.content)

        overhead = len(messages) * 5 # for roles/etc...
        return cls.estimate_from_text("x" * total_chars) + overhead
    
__all__ = [
    "ModelType",
    "RoutingReasonCategory",
    "RoutingReason",
    "GenerationParams",
    "RouterDecision",
    "RequestMetadata",
    "TokenEstimator",
]