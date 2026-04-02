"""
Parrrot — Cloud providers via OpenAI-compatible API
Supports: OpenAI, Anthropic (via openai-compat), Groq, Google Gemini, custom
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

import httpx

from .base import BaseLLM, CompletionRequest, CompletionResponse

# Provider endpoint registry
_PROVIDER_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    # MiniMax provides an OpenAI-compatible API but with a different endpoint.
    "minimax": "https://api.minimax.io/v1",
    # Kimi (Moonshot) is OpenAI-compatible.
    "kimi": "https://api.moonshot.ai/v1",
}


def _load_api_key(provider: str) -> str:
    """Load API key from encrypted secrets or environment variable."""
    import os

    # Check env vars first
    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "google": "GOOGLE_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "kimi": "KIMI_API_KEY",
    }
    env_var = env_map.get(provider)
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]

    # Try encrypted secrets file
    secrets_path = Path.home() / ".parrrot" / "secrets.json"
    key_path = Path.home() / ".parrrot" / ".key"
    if secrets_path.exists() and key_path.exists():
        try:
            from cryptography.fernet import Fernet

            key = key_path.read_bytes()
            fernet = Fernet(key)
            secrets = json.loads(secrets_path.read_text())
            encrypted = secrets.get(f"{provider}_api_key", "")
            if encrypted:
                return fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            # Fall back to unencrypted
            secrets = json.loads(secrets_path.read_text())
            return secrets.get(f"{provider}_api_key", "")

    return ""


class OllamaCloudLLM(BaseLLM):
    """
    Calls cloud LLM providers via the OpenAI-compatible chat completions API.
    All major providers expose this format.
    """

    def __init__(
        self,
        model: str,
        provider: str = "openai",
        base_url: str = "",
        api_key: str = "",
    ) -> None:
        self._model = model
        self._provider = provider
        self._base_url = base_url or _PROVIDER_ENDPOINTS.get(provider, "")
        self._api_key = api_key or _load_api_key(provider)

    @property
    def model_name(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        # Anthropic requires extra headers
        if self._provider == "anthropic":
            h["anthropic-version"] = "2023-06-01"
            h["x-api-key"] = self._api_key
        return h

    def _chat_completions_path(self) -> str:
        """
        Some OpenAI-compat providers use non-standard paths.
        Returns path relative to `_base_url`.
        """
        if self._provider == "minimax":
            # MiniMax uses:
            # POST /v1/text/chatcompletion_v2
            # Where `_base_url` is typically https://api.minimax.io/v1
            return "/text/chatcompletion_v2"
        return "/chat/completions"

    def _extract_content_from_completion(self, data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is not None:
            return str(content)
        # Some providers may return `text` instead of `message.content`
        text = choices[0].get("text")
        if text is not None:
            return str(text)
        return ""

    def _build_messages(self, request: CompletionRequest) -> list[dict]:
        msgs = []
        if request.system:
            msgs.append({"role": "system", "content": request.system})
        for msg in request.messages:
            msgs.append({"role": msg.role, "content": msg.content})
        return msgs

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self._base_url}/models", headers=self._headers())
                return r.status_code in (200, 401)  # 401 = reachable but key wrong
        except Exception:
            return False

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload = {
            "model": self._model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{self._base_url}{self._chat_completions_path()}",
                json=payload,
                headers=self._headers(),
            )
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                body = r.text
                raise RuntimeError(
                    f"Cloud LLM error ({r.status_code}): {body}"
                ) from e
            data = r.json()

        content = self._extract_content_from_completion(data)
        usage = data.get("usage", {})
        return CompletionResponse(
            content=content,
            model=data.get("model", self._model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}{self._chat_completions_path()}",
                json=payload,
                headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    try:
                        data = json.loads(line)
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        # Prefer content, but tolerate providers that use `text`
                        token = (
                            delta.get("content")
                            or delta.get("text")
                            or delta.get("delta")
                            or ""
                        )
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
