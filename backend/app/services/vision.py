from __future__ import annotations

import base64
from contextvars import ContextVar
from dataclasses import dataclass
import time
from typing import Any

import litellm


FALLBACK_MODEL_PRICING_USD_PER_TOKEN: dict[str, tuple[float, float]] = {
    "gemini/gemini-3.5-flash-lite": (3e-07, 2.5e-06),
    "gemini/gemini-2.5-flash-lite": (1e-07, 4e-07),
    "gemini/gemini-2.5-flash": (3e-07, 2.5e-06),
    "gemini/gemini-2.5-pro": (1.25e-06, 1e-05),
    "gemini/gemini-3.5-flash": (3e-07, 2.5e-06),
    "openai/gpt-4o-mini": (1.5e-07, 6e-07),
    "openai/gpt-4o": (2.5e-06, 1e-05),
    "anthropic/claude-sonnet-4-5": (3e-06, 1.5e-05),
}

_last_vision_usage: ContextVar[dict[str, Any] | None] = ContextVar("_last_vision_usage", default=None)


def reset_last_vision_usage() -> None:
    """Clear any stored usage metrics from prior vision calls in this async context."""
    _last_vision_usage.set(None)


def consume_last_vision_usage() -> dict[str, Any] | None:
    """Pop and return the most recent vision usage dictionary in this async context."""
    usage = _last_vision_usage.get()
    _last_vision_usage.set(None)
    return dict(usage) if usage else None


def get_model_pricing(model: str) -> tuple[float, float]:
    """Return (input_cost_per_token, output_cost_per_token) in USD."""
    candidates = [model, model.split("/", 1)[-1]]
    for key in candidates:
        info = litellm.model_cost.get(key)
        if isinstance(info, dict):
            inp = info.get("input_cost_per_token")
            out = info.get("output_cost_per_token")
            if inp is not None and out is not None:
                return float(inp), float(out)
    if model in FALLBACK_MODEL_PRICING_USD_PER_TOKEN:
        return FALLBACK_MODEL_PRICING_USD_PER_TOKEN[model]
    return (0.0, 0.0)


def estimate_model_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from token counts using LiteLLM pricing table or fallback."""
    inp_rate, out_rate = get_model_pricing(model)
    return round((max(0, prompt_tokens) * inp_rate) + (max(0, completion_tokens) * out_rate), 8)


def _extract_usage_dict(response: Any, *, model: str, latency_ms: int) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if isinstance(usage, dict):
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    elif usage is not None:
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens))
    else:
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

    cost_usd = 0.0
    cost_source = "estimate"
    hidden = getattr(response, "_hidden_params", None)
    if isinstance(hidden, dict) and hidden.get("response_cost") is not None:
        try:
            cost_usd = float(hidden["response_cost"])
            cost_source = "provider"
        except (TypeError, ValueError):
            cost_usd = 0.0
    if cost_usd <= 0.0 and (prompt_tokens > 0 or completion_tokens > 0):
        try:
            cost_usd = float(litellm.completion_cost(completion_response=response) or 0.0)
            if cost_usd > 0.0:
                cost_source = "litellm"
        except Exception:
            cost_usd = 0.0
    if cost_usd <= 0.0 and (prompt_tokens > 0 or completion_tokens > 0):
        cost_usd = estimate_model_cost(model, prompt_tokens, completion_tokens)
        cost_source = "catalog_estimate"

    return {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 8),
        "cost_source": cost_source,
        "latency_ms": max(0, int(latency_ms)),
    }


class VisionResponseError(RuntimeError):
    """Raised when the provider returns an unusable response."""


@dataclass(frozen=True)
class VisionImage:
    """One uploaded image and the slot it belongs to."""

    slot: str
    filename: str
    content_type: str
    data: bytes


def _image_data_uri(image: VisionImage) -> str:
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{image.content_type};base64,{encoded}"


def build_messages(prompt: str, images: list[VisionImage], *, detail: str = "high") -> list[dict[str, Any]]:
    """Build an OpenAI-style multimodal message with labeled images."""
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    if not images:
        raise ValueError("at least one image is required")

    content: list[dict[str, Any]] = []
    for image in images:
        content.append({"type": "text", "text": f"SLOT {image.slot} - {image.filename}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": _image_data_uri(image),
                    "detail": detail,
                },
            }
        )

    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": content},
    ]


def _supports_temperature(model: str) -> bool:
    try:
        params = litellm.get_supported_openai_params(model=model)
    except Exception:
        return True
    return params is None or "temperature" in params


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    raise VisionResponseError("provider returned empty or unsupported message content")


async def complete_vision(
    *,
    model: str,
    prompt: str,
    images: list[VisionImage],
    response_format: dict[str, Any] | type | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    timeout: float = 120.0,
    num_retries: int = 2,
    detail: str = "high",
    api_key: str | None = None,
) -> str:
    """Send one multimodal request to the configured LiteLLM model and return its text."""
    messages = build_messages(prompt, images, detail=detail)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "num_retries": num_retries,
    }
    if _supports_temperature(model):
        kwargs["temperature"] = temperature
    if response_format is not None:
        kwargs["response_format"] = response_format
    if api_key is not None:
        kwargs["api_key"] = api_key

    started = time.perf_counter()
    response = await litellm.acompletion(**kwargs)
    latency_ms = int(round((time.perf_counter() - started) * 1000))
    _last_vision_usage.set(_extract_usage_dict(response, model=model, latency_ms=latency_ms))

    if not response.choices:
        raise VisionResponseError("provider returned no choices")
    return _content_to_text(response.choices[0].message.content)
