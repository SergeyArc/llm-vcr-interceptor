from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_STREAM_MAX_BODY_BYTES = 10 * 1024 * 1024
_STREAM_MAX_BODY_ENV = "LHI_STREAM_MAX_BODY_BYTES"
_SSE_CONTENT_TYPE = "text/event-stream"


def _as_header_value(raw_value: Any) -> str:
    if isinstance(raw_value, list):
        return ", ".join(str(item) for item in raw_value)
    return str(raw_value)


def _get_header_case_insensitive(headers: Mapping[str, Any], target_name: str) -> str:
    for header_name, header_value in headers.items():
        if str(header_name).lower() == target_name.lower():
            return _as_header_value(header_value)
    return ""


def _normalize_body_string(response: Mapping[str, Any]) -> bytes:
    raw_body = (response.get("body") or {}).get("string")
    if isinstance(raw_body, bytes):
        return raw_body
    if isinstance(raw_body, str):
        return raw_body.encode("utf-8")
    return b""


def _stream_max_body_bytes() -> int:
    raw_value = os.environ.get(_STREAM_MAX_BODY_ENV)
    if raw_value is None:
        return DEFAULT_STREAM_MAX_BODY_BYTES
    try:
        parsed_value = int(raw_value)
    except ValueError as exc:
        msg = f"{_STREAM_MAX_BODY_ENV} must be an integer, got: {raw_value!r}"
        raise ValueError(msg) from exc
    if parsed_value <= 0:
        msg = f"{_STREAM_MAX_BODY_ENV} must be > 0, got: {parsed_value}"
        raise ValueError(msg)
    return parsed_value


def is_streaming_response(response: Mapping[str, Any]) -> bool:
    headers = response.get("headers") or {}
    if not isinstance(headers, Mapping):
        return False
    content_type = _get_header_case_insensitive(headers, "content-type").lower()
    transfer_encoding = _get_header_case_insensitive(headers, "transfer-encoding").lower()
    if _SSE_CONTENT_TYPE in content_type:
        return True
    if "chunked" in transfer_encoding:
        return True
    body_bytes = _normalize_body_string(response)
    return b"data:" in body_bytes and b"\n\n" in body_bytes


def split_sse_body(body: bytes) -> Iterator[bytes]:
    if not body:
        return
    for raw_event in body.split(b"\n\n"):
        if not raw_event:
            continue
        yield raw_event + b"\n\n"


def normalize_streaming_response(response: dict[str, Any]) -> dict[str, Any]:
    if not is_streaming_response(response):
        return response
    body_bytes = _normalize_body_string(response)
    max_body_size = _stream_max_body_bytes()
    if len(body_bytes) > max_body_size:
        msg = (
            f"SSE body is too large ({len(body_bytes)} bytes), "
            f"max allowed is {max_body_size} bytes. "
            f"Increase {_STREAM_MAX_BODY_ENV} if this is expected."
        )
        raise ValueError(msg)
    normalized_response = dict(response)
    headers = normalized_response.get("headers") or {}
    if not isinstance(headers, Mapping):
        headers = {}
    cleaned_headers: dict[str, Any] = {}
    for header_name, header_value in headers.items():
        lower_name = str(header_name).lower()
        if lower_name in {"transfer-encoding", "content-length"}:
            continue
        cleaned_headers[str(header_name)] = header_value
    normalized_response["headers"] = cleaned_headers
    normalized_response["body"] = {"string": body_bytes.decode("utf-8")}
    return normalized_response


@dataclass
class CursorByteStream:
    _chunks: tuple[bytes, ...]
    _cursor: int = 0

    @classmethod
    def from_sse_body(cls, body: bytes) -> CursorByteStream:
        return cls(tuple(split_sse_body(body)))

    def __iter__(self) -> Iterator[bytes]:
        while self._cursor < len(self._chunks):
            chunk = self._chunks[self._cursor]
            self._cursor += 1
            yield chunk

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while self._cursor < len(self._chunks):
            chunk = self._chunks[self._cursor]
            self._cursor += 1
            yield chunk


def apply_replay_streaming_shim(vcr_response: dict[str, Any], real_response: Any) -> Any:
    if not is_streaming_response(vcr_response):
        return real_response
    body_bytes = _normalize_body_string(vcr_response)
    real_response.stream = CursorByteStream.from_sse_body(body_bytes)
    return real_response
