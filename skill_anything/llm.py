# -*- coding: utf-8 -*-
"""Shared LLM client — loads config from .env, supports chat and image generation."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_env_loaded = False


def _allows_custom_temperature(model: str) -> bool:
    """Return whether a model family accepts non-default temperature values."""
    normalized = model.lower()
    return not normalized.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


def _ensure_env() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    try:
        from dotenv import load_dotenv

        for candidate in [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]:
            if candidate.exists():
                load_dotenv(candidate, override=False)
                return
    except ImportError:
        pass


def _get_client() -> tuple[Any, str]:
    """Return ``(OpenAI_client | None, model_name)``."""
    _ensure_env()

    api_key = os.getenv("SKILL_ANYTHING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("SKILL_ANYTHING_API_BASE") or os.getenv("OPENAI_API_BASE")
    proxy = os.getenv("SKILL_ANYTHING_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    model = os.getenv("SKILL_ANYTHING_MODEL", "gpt-4o")

    if not api_key:
        return None, model

    try:
        from openai import OpenAI
    except ImportError:
        return None, model

    kwargs: dict[str, Any] = {"api_key": api_key}
    if api_base:
        kwargs["base_url"] = api_base
    if proxy:
        try:
            import httpx
            kwargs["http_client"] = httpx.Client(proxy=proxy, timeout=120.0)
        except ImportError:
            pass

    return OpenAI(**kwargs), model


def _get_image_client() -> tuple[Any, str]:
    """Return ``(OpenAI_client | None, model_name)`` for image generation."""
    _ensure_env()

    api_key = os.getenv("SKILL_ANYTHING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("SKILL_ANYTHING_IMAGE_API_BASE") or os.getenv("SKILL_ANYTHING_API_BASE") or os.getenv("OPENAI_API_BASE")
    proxy = os.getenv("SKILL_ANYTHING_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    model = os.getenv("SKILL_ANYTHING_IMAGE_MODEL", "dall-e-3")

    if not api_key:
        return None, model

    try:
        from openai import OpenAI
    except ImportError:
        return None, model

    kwargs: dict[str, Any] = {"api_key": api_key}
    if api_base:
        kwargs["base_url"] = api_base
    if proxy:
        try:
            import httpx
            kwargs["http_client"] = httpx.Client(proxy=proxy, timeout=120.0)
        except ImportError:
            pass

    return OpenAI(**kwargs), model


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model: str | None = None,
) -> str | None:
    """Send a chat completion request; returns response text or *None* on failure."""
    client, configured_model = _get_client()
    selected_model = model or configured_model

    if client is None:
        # ``httpx`` is already a core dependency. Keeping this small fallback
        # means chat still works in constrained installs where the optional
        # OpenAI SDK is absent, and with any OpenAI-compatible endpoint.
        _ensure_env()
        api_key = os.getenv("SKILL_ANYTHING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return None
        api_base = (
            os.getenv("SKILL_ANYTHING_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or "https://api.openai.com/v1"
        )
        proxy = (
            os.getenv("SKILL_ANYTHING_PROXY")
            or os.getenv("HTTPS_PROXY")
            or os.getenv("HTTP_PROXY")
        )
        import httpx

        client_kwargs: dict[str, Any] = {"timeout": 120.0}
        if proxy:
            client_kwargs["proxy"] = proxy
        request_data: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if _allows_custom_temperature(selected_model):
            request_data["temperature"] = temperature
        with httpx.Client(**client_kwargs) as http_client:
            response = http_client.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=request_data,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"].get("content")
        return content.strip() if content else None

    request_kwargs: dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if _allows_custom_temperature(selected_model):
        request_kwargs["temperature"] = temperature
    resp = client.chat.completions.create(
        **request_kwargs,
    )
    content = resp.choices[0].message.content
    return content.strip() if content else None


def generate_image(
    prompt: str,
    *,
    size: str = "1024x1024",
    output_path: str | None = None,
) -> str | None:
    """Generate an image from a text prompt.

    Returns the file path if output_path is given, otherwise the URL.
    Returns None on failure.
    """
    client, model = _get_image_client()
    if client is None:
        return None

    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
        }
        if output_path:
            kwargs["response_format"] = "b64_json"

        resp = client.images.generate(**kwargs)

        if output_path:
            b64_data = resp.data[0].b64_json
            if b64_data:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(b64_data))
                return output_path
            return None
        else:
            return resp.data[0].url
    except Exception as e:
        log.warning("Image generation failed: %s", e)
        return None


def is_available() -> bool:
    """Check whether an LLM backend is configured and reachable."""
    _ensure_env()
    api_key = os.getenv("SKILL_ANYTHING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    return bool(api_key)
