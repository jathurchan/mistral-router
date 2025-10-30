"""
App configuration for Mistral Router.

Loads and validates application settings from environment variables via Pydantic.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""

    # Mistral API
    mistral_api_key: str
    mistral_api_base_url: str = "https://api.mistral.ai/v1"

    # Router
    router_api_key: Optional[str] = None  # Optional; falls back to mistral_api_key if unset
    router_length_threshold: int = 120
    router_token_threshold: int = 150
    router_conversation_threshold: int = 6
    router_client_timeout_s: int = 15
    router_health_check_timeout_s: float = 5.0

    # Models
    model_small: str = "mistral-small-latest"
    model_medium: str = "mistral-medium-latest"

    # Pricing (USD / 1M tokens)
    price_small_input: float = 0.1
    price_small_output: float = 0.3
    price_medium_input: float = 0.4
    price_medium_output: float = 2.0

    # Logging
    log_level: str = "INFO"
    service_name: str = "mistral-router"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()   # type: ignore