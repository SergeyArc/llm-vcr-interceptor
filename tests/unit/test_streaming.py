from __future__ import annotations

from typing import Any

import pytest

from lhi.streaming import (
    DEFAULT_STREAM_MAX_BODY_BYTES,
    CursorByteStream,
    is_streaming_response,
    normalize_streaming_response,
    split_sse_body,
)


def test_is_streaming_response_detects_sse_content_type() -> None:
    response: dict[str, Any] = {
        "headers": {"Content-Type": ["text/event-stream"]},
        "body": {"string": b"data: hello\n\n"},
    }
    assert is_streaming_response(response) is True


def test_split_sse_body_preserves_event_delimiter() -> None:
    chunks = list(split_sse_body(b"data: first\n\ndata: second\n\n"))
    assert chunks == [b"data: first\n\n", b"data: second\n\n"]


def test_normalize_streaming_response_drops_transport_headers() -> None:
    response: dict[str, Any] = {
        "headers": {
            "Content-Type": ["text/event-stream"],
            "Transfer-Encoding": ["chunked"],
            "Content-Length": ["42"],
        },
        "body": {"string": "data: hello\n\n"},
    }
    normalized = normalize_streaming_response(response)
    assert normalized["body"]["string"] == "data: hello\n\n"
    assert "Transfer-Encoding" not in normalized["headers"]
    assert "Content-Length" not in normalized["headers"]


def test_normalize_streaming_response_enforces_body_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LHI_STREAM_MAX_BODY_BYTES", "4")
    response: dict[str, Any] = {
        "headers": {"Content-Type": ["text/event-stream"]},
        "body": {"string": b"data: too-big\n\n"},
    }
    with pytest.raises(ValueError, match="SSE body is too large"):
        normalize_streaming_response(response)


def test_cursor_byte_stream_does_not_restart_after_first_iteration() -> None:
    stream = CursorByteStream.from_sse_body(b"data: first\n\ndata: second\n\n")
    assert list(stream) == [b"data: first\n\n", b"data: second\n\n"]
    assert list(stream) == []


def test_default_stream_limit_is_positive() -> None:
    assert DEFAULT_STREAM_MAX_BODY_BYTES > 0
