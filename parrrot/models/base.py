"""
Parrrot — Abstract LLM interface
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_name: str | None = None
    tool_result: str | None = None


@dataclass
class CompletionRequest:
    messages: list[Message]
    system: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    images: list[bytes] = field(default_factory=list)  # for vision models


@dataclass
class CompletionResponse:
    content: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    done: bool = True


class BaseLLM(ABC):
    """Abstract interface all LLM backends must implement."""

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return a single completion."""
        ...

    @abstractmethod
    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Yield completion tokens one at a time."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the backend is reachable."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string."""
        ...
