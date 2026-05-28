"""Small async client wrapper that keeps the existing `OllamaClient` API
but can optionally proxy requests to OpenAI when `OPENAI_API_KEY` is set.

This lets the rest of the code continue to import and type against
`OllamaClient` while avoiding a dependency on the local Ollama runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import os

import httpx


@dataclass
class OllamaUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class OllamaMessage:
    content: str


@dataclass
class OllamaChoice:
    message: OllamaMessage


@dataclass
class OllamaResponse:
    choices: list[OllamaChoice]
    usage: OllamaUsage = field(default_factory=OllamaUsage)
    raw: dict[str, Any] = field(default_factory=dict)


class _OllamaChatCompletions:
    def __init__(self, client: "OllamaClient"):
        self._client = client

    async def create(
        self,
        *,
        model: Optional[str] = None,
        messages: list[dict[str, str]],
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        temperature: Optional[float] = None,
        **_: Any,
    ) -> OllamaResponse:
        return await self._client._create_chat_completion(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=temperature,
        )


class _OllamaChatAPI:
    def __init__(self, client: "OllamaClient"):
        self.completions = _OllamaChatCompletions(client)


class OllamaClient:
    """Compatibility client.

    If `OPENAI_API_KEY` is present in the environment (or `api_key` is
    provided), requests are sent to OpenAI's chat completions endpoint.
    Otherwise behavior falls back to the local Ollama API at `base_url`.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "phi3:mini",
        timeout: float = 60.0,
        max_retries: int = 0,
        api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        groq_base_url: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = model
        self.timeout = timeout
        self.max_retries = max_retries
        # Prefer explicit provider arguments; only fall back to environment when
        # the caller leaves them as None. An explicit empty string disables the
        # provider, which is important for local-only fallbacks.
        self.openai_api_key = os.getenv("OPENAI_API_KEY") if api_key is None else api_key
        self.groq_api_key = os.getenv("GROQ_API_KEY") if groq_api_key is None else groq_api_key
        self.groq_base_url = (groq_base_url or os.getenv("GROQ_BASE_URL") or "https://api.groq.com").rstrip("/")
        self.chat = _OllamaChatAPI(self)

    def with_options(
        self,
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> "OllamaClient":
        return OllamaClient(
            base_url=self.base_url,
            model=self.default_model,
            timeout=self.timeout if timeout is None else timeout,
            max_retries=self.max_retries if max_retries is None else max_retries,
            api_key=self.openai_api_key,
            groq_api_key=self.groq_api_key,
            groq_base_url=self.groq_base_url,
        )

    async def _create_chat_completion(
        self,
        *,
        model: Optional[str],
        messages: list[dict[str, str]],
        max_tokens: Optional[int],
        timeout: Optional[float],
        temperature: Optional[float],
    ) -> OllamaResponse:
        use_groq = bool(self.groq_api_key)
        use_openai = bool(self.openai_api_key) and not use_groq
        request_timeout = timeout if timeout is not None else self.timeout
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                if use_groq:
                    # Call Groq chat completions endpoint.
                    # Use GROQ API key and base URL from env or constructor.
                    headers = {"Authorization": f"Bearer {self.groq_api_key}"}
                    payload = {
                        "model": model or self.default_model,
                        "messages": messages,
                    }
                    if max_tokens is not None:
                        payload["max_tokens"] = max_tokens
                    if temperature is not None:
                        payload["temperature"] = temperature

                    async with httpx.AsyncClient(timeout=request_timeout) as client:
                        data = None
                        # Try common Groq endpoints in case the base path differs
                        for path in ("/openai/v1/chat/completions", "/v1/chat/completions", "/chat/completions"):
                            url = f"{self.groq_base_url}{path}"
                            resp = await client.post(url, headers={**headers, "Content-Type": "application/json"}, json=payload)
                            if resp.status_code == 404:
                                continue
                            resp.raise_for_status()
                            data = resp.json()
                            break
                        if data is None:
                            # If we didn't find a working endpoint, raise the last response error
                            resp.raise_for_status()

                    # Groq's response generally follows the OpenAI-style shape; fall back safely
                    choice = data.get("choices", [{}])[0]
                    message = choice.get("message", {}) if isinstance(choice, dict) else {}
                    content = message.get("content") or choice.get("text") or ""
                    usage = OllamaUsage(
                        input_tokens=int(data.get("usage", {}).get("prompt_tokens", 0) or 0) if isinstance(data.get("usage"), dict) else 0,
                        output_tokens=int(data.get("usage", {}).get("completion_tokens", 0) or 0) if isinstance(data.get("usage"), dict) else 0,
                    )
                    return OllamaResponse(
                        choices=[OllamaChoice(message=OllamaMessage(content=content))],
                        usage=usage,
                        raw=data,
                    )
                elif use_openai:
                    # Call OpenAI Chat Completions
                    headers = {"Authorization": f"Bearer {self.openai_api_key}"}
                    payload = {
                        "model": model or self.default_model,
                        "messages": messages,
                    }
                    if max_tokens is not None:
                        payload["max_tokens"] = max_tokens
                    if temperature is not None:
                        payload["temperature"] = temperature

                    async with httpx.AsyncClient(timeout=request_timeout) as client:
                        resp = await client.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={**headers, "Content-Type": "application/json"},
                            json=payload,
                        )
                        resp.raise_for_status()
                        data = resp.json()

                    choice = data.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    content = message.get("content", "")
                    usage = OllamaUsage(
                        input_tokens=int(data.get("usage", {}).get("prompt_tokens", 0) or 0),
                        output_tokens=int(data.get("usage", {}).get("completion_tokens", 0) or 0),
                    )
                    return OllamaResponse(
                        choices=[OllamaChoice(message=OllamaMessage(content=content))],
                        usage=usage,
                        raw=data,
                    )
                else:
                    # Call local Ollama runtime
                    payload: dict[str, Any] = {
                        "model": model or self.default_model,
                        "messages": messages,
                        "stream": False,
                    }
                    options: dict[str, Any] = {}
                    if max_tokens is not None:
                        options["num_predict"] = max_tokens
                    if temperature is not None:
                        options["temperature"] = temperature
                    if options:
                        payload["options"] = options

                    async with httpx.AsyncClient(base_url=self.base_url, timeout=request_timeout) as client:
                        response = await client.post("/api/chat", json=payload)
                        response.raise_for_status()
                        data = response.json()

                    message = data.get("message") or {}
                    content = message.get("content", "")
                    usage = OllamaUsage(
                        input_tokens=int(data.get("prompt_eval_count", 0) or 0),
                        output_tokens=int(data.get("eval_count", 0) or 0),
                    )
                    return OllamaResponse(
                        choices=[OllamaChoice(message=OllamaMessage(content=content))],
                        usage=usage,
                        raw=data,
                    )
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break

        assert last_error is not None
        raise last_error
