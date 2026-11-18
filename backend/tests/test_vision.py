import asyncio
import base64
from types import SimpleNamespace

import pytest

from app.services import vision


def _image(slot: str, filename: str, payload: bytes) -> vision.VisionImage:
    return vision.VisionImage(
        slot=slot,
        filename=filename,
        content_type="image/jpeg",
        data=payload,
    )


def test_build_messages_labels_images_and_encodes_data_uri() -> None:
    images = [
        _image("A", "slot-a.jpg", b"first-image"),
        _image("B", "slot-b.jpg", b"second-image"),
    ]

    messages = vision.build_messages("Extract the receipts.", images)

    assert messages[0] == {"role": "system", "content": "Extract the receipts."}
    content = messages[1]["content"]
    assert content[0] == {"type": "text", "text": "SLOT A - slot-a.jpg"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["detail"] == "high"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1]) == b"first-image"
    assert content[2] == {"type": "text", "text": "SLOT B - slot-b.jpg"}
    assert content[3]["type"] == "image_url"
    assert base64.b64decode(content[3]["image_url"]["url"].split(",", 1)[1]) == b"second-image"


def test_complete_vision_passes_litellm_options_and_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"document_type": "invoice"}'))]
        )

    monkeypatch.setattr(vision.litellm, "acompletion", fake_acompletion)

    result = asyncio.run(
        vision.complete_vision(
            model="gemini/gemini-2.5-flash",
            prompt="Extract the receipts.",
            images=[_image("A", "slot-a.jpg", b"first-image")],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2048,
            timeout=30.0,
            num_retries=1,
        )
    )

    assert result == '{"document_type": "invoice"}'
    assert captured["model"] == "gemini/gemini-2.5-flash"
    assert captured["temperature"] == 0.1
    assert captured["max_tokens"] == 2048
    assert captured["timeout"] == 30.0
    assert captured["num_retries"] == 1
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][1]["content"][0]["text"] == "SLOT A - slot-a.jpg"


def test_complete_vision_normalizes_list_content(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_acompletion(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=[
                            {"type": "text", "text": '{"a": 1}'},
                            {"type": "text", "text": '{"b": 2}'},
                        ]
                    )
                )
            ]
        )

    monkeypatch.setattr(vision.litellm, "acompletion", fake_acompletion)

    result = asyncio.run(
        vision.complete_vision(
            model="anthropic/claude-sonnet-4-5",
            prompt="Extract the receipts.",
            images=[_image("A", "slot-a.jpg", b"first-image")],
        )
    )

    assert result == '{"a": 1}{"b": 2}'


def test_build_messages_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        vision.build_messages("", [_image("A", "slot-a.jpg", b"first-image")])

    with pytest.raises(ValueError):
        vision.build_messages("Extract the receipts.", [])
