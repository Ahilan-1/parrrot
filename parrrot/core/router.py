"""
Parrrot — LLM router (local / cloud / hybrid)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

from typing import AsyncIterator

from parrrot import config as cfg
from parrrot.models.base import BaseLLM, CompletionRequest, CompletionResponse


def _build_local(conf: dict) -> BaseLLM:
    from parrrot.models.ollama_local import OllamaLocalLLM

    return OllamaLocalLLM(
        model=conf["model"].get("local_model", "llama3.2"),
        base_url=conf["model"].get("local_url", "http://localhost:11434"),
    )


def _build_cloud(conf: dict) -> BaseLLM:
    from parrrot.models.ollama_cloud import OllamaCloudLLM

    def _normalize_model(provider: str, model: str) -> str:
        # Users often pass Ollama-style tags like "kimi-k2.5:cloud".
        # For OpenAI-compatible cloud APIs we should strip the suffix.
        if not model:
            return model
        if provider in ("kimi", "minimax") and ":" in model:
            return model.split(":", 1)[0]
        return model

    provider = conf["model"].get("cloud_provider", "openai")
    raw_model = conf["model"].get("cloud_model", "gpt-4o-mini")

    return OllamaCloudLLM(
        model=_normalize_model(provider, raw_model),
        provider=provider,
        base_url=conf["model"].get("cloud_endpoint", ""),
    )


class Router:
    """Selects and calls the right LLM backend based on config."""

    def __init__(self) -> None:
        self._conf = cfg.load()
        self._mode = self._conf["model"].get("mode", "local")
        self._local: BaseLLM | None = None
        self._cloud: BaseLLM | None = None
        self._load_backends()

    def _load_backends(self) -> None:
        if self._mode in ("local", "hybrid"):
            self._local = _build_local(self._conf)
        if self._mode in ("cloud", "hybrid"):
            self._cloud = _build_cloud(self._conf)

    def _pick_backend(self, force_cloud: bool = False) -> BaseLLM:
        if force_cloud and self._cloud:
            return self._cloud
        if self._mode == "cloud":
            if not self._cloud:
                raise RuntimeError("Cloud model not configured. Run: parrrot config")
            return self._cloud
        if self._mode == "hybrid":
            threshold = self._conf["model"].get("hybrid_threshold", "auto")
            if threshold == "never" or not self._cloud:
                return self._local  # type: ignore[return-value]
            if threshold == "manual" and not force_cloud:
                return self._local  # type: ignore[return-value]
            # "auto" — use local; cloud escalation handled by agent
            return self._local  # type: ignore[return-value]
        # local
        if not self._local:
            raise RuntimeError("Local Ollama not configured.")
        return self._local

    async def complete(
        self,
        request: CompletionRequest,
        force_cloud: bool = False,
    ) -> CompletionResponse:
        backend = self._pick_backend(force_cloud)
        return await backend.complete(request)

    async def stream(
        self,
        request: CompletionRequest,
        force_cloud: bool = False,
    ) -> AsyncIterator[str]:
        backend = self._pick_backend(force_cloud)
        return backend.stream(request)

    async def health_check(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        if self._local:
            results["local"] = await self._local.health_check()
        if self._cloud:
            results["cloud"] = await self._cloud.health_check()
        return results

    @property
    def active_model(self) -> str:
        backend = self._pick_backend()
        return backend.model_name
