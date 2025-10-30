"""
Pydantic models for request/response validation.
Covers the Mistral chat/completions API with all parameters.
"""

from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum

class FunctionDefinition(BaseModel):
    """Function definition for tool calling."""
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any]

class Tool(BaseModel):
    """Tool definition."""
    type: Literal["function"] = "function"
    function: FunctionDefinition

class MessageRole(str, Enum):
    """Chat roles."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class ToolCall(BaseModel):
    """Tool call made by assistant."""
    id: str
    type: Literal["function"] = "function"
    function: Dict[str, Any]

class BaseMessage(BaseModel):
    """Common message fields."""
    role: str
    content: Optional[str] = None

class SystemMessage(BaseMessage):
    """System instruction."""
    role: Literal["system"] = "system"
    content: str

class UserMessage(BaseMessage):
    """User input."""
    role: Literal["user"] = "user"
    content: str

class AssistantMessage(BaseMessage):
    """Assistant reply."""
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None

class ToolMessage(BaseMessage):
    """Tool output."""
    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str

Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]

class ChatCompletionRequest(BaseModel):
    """
    Request schema for /v1/chat/completions.
    Fully compatible with the Mistral API, with added 'auto' model routing.
    """
    
    model: str = Field(
        ...,
        description="Model ID ('mistral-small-latest', 'mistral-medium-latest', or 'auto')."
    )
    messages: List[Message] = Field(..., min_length=1)
    
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    
    stop: Optional[Union[str, List[str]]] = None
    stream: Optional[bool] = Field(default=False)
    random_seed: Optional[int] = None
    safe_prompt: Optional[bool] = False

    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto"

    response_format: Optional[Dict[str, str]] = None
    
    @model_validator(mode='after')
    def validate_request(self) -> 'ChatCompletionRequest':
        """Validate message content requirements."""
        for msg in self.messages:
            if isinstance(msg, SystemMessage) and not msg.content:
                raise ValueError("System message requires content")
            
            if isinstance(msg, UserMessage) and not msg.content:
                raise ValueError("User message requires content")
            
            if isinstance(msg, AssistantMessage):
                if not msg.content and not msg.tool_calls:
                    raise ValueError(
                        "Assistant message must have content or tool_calls"
                    )
            
            if isinstance(msg, ToolMessage):
                if not msg.content:
                    raise ValueError("Tool message requires content")
                if not msg.tool_call_id:
                    raise ValueError("Tool message requires tool_call_id")
        
        return self
    
    @model_validator(mode='after')
    def validate_streaming(self) -> 'ChatCompletionRequest':
        """Reject streaming for now (MVP)."""
        if self.stream:
            raise ValueError("Streaming is not supported in this version")
        return self

class UsageInfo(BaseModel):
    """Token counts."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionChoice(BaseModel):
    """Single choice."""
    index: int
    message: AssistantMessage
    finish_reason: Optional[str] = None

class ChatCompletionResponse(BaseModel):
    """Standard Mistral-compatible response."""
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[UsageInfo] = None

class ErrorDetail(BaseModel):
    message: str
    type: str
    code: Optional[str] = None

class ErrorResponse(BaseModel):
    """Standardized error wrapper."""
    error: ErrorDetail

class HealthResponse(BaseModel):
    """Health check."""
    status: Literal["healthy"]
    service: str = "mistral-router"
    version: str = "1.0.0"