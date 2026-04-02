"""
Parrrot — Ollama local backend (http://localhost:11434)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import base64
import json
from typing import AsyncIterator

import httpx

from .base import BaseLLM, CompletionRequest, CompletionResponse, Message


class OllamaLocalLLM(BaseLLM):
    """Calls a locally running Ollama server."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def model_name(self) -> str:
        return self._model

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self._base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    def _build_messages(self, request: CompletionRequest) -> list[dict]:
        msgs = []
        if request.system:
            msgs.append({"role": "system", "content": request.system})
        for msg in request.messages:
            entry: dict = {"role": msg.role, "content": msg.content}
            msgs.append(entry)
        return msgs

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        msgs = self._build_messages(request)
        payload: dict = {
            "model": self._model,
            "messages": msgs,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if request.images:
            # Attach images to the last user message for vision models
            for msg in reversed(payload["messages"]):
                if msg["role"] == "user":
                    msg["images"] = [base64.b64encode(img).decode() for img in request.images]
                    break

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{self._base_url}/api/chat", json=payload)
            if r.status_code == 400 and request.images:
                raise RuntimeError(
                    f"Model '{self._model}' does not support vision/images.\n"
                    f"Install a vision model: ollama pull llava\n"
                    f"Then set it in ~/.parrrot/config.toml: local_model = 'llava'"
                )
            r.raise_for_status()
            data = r.json()

        content = data.get("message", {}).get("content", "")
        return CompletionResponse(
            content=content,
            model=data.get("model", self._model),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        msgs = self._build_messages(request)
        payload: dict = {
            "model": self._model,
            "messages": msgs,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    async def pull_model(self, on_progress=None) -> None:
        """Pull (download) the model from Ollama registry."""
        payload = {"name": self._model, "stream": True}
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/pull", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if on_progress:
                            on_progress(data)
                        if data.get("status") == "success":
                            break
                    except json.JSONDecodeError:
                        continue
