from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import litellm


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

    response = await litellm.acompletion(**kwargs)

    if not response.choices:
        raise VisionResponseError("provider returned no choices")
    return _content_to_text(response.choices[0].message.content)
