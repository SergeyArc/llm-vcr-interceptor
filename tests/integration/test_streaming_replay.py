from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from lhi import LHIInterceptor, invocation_context


def _sse_body() -> str:
    return "data: first\n\ndata: second\n\n"


def test_streaming_replay_iter_lines_sync(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag="sse_sync",
                uri="http://example.com/sse",
                body=_sse_body(),
                content_type="text/event-stream",
            ),
        ],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        with invocation_context("sse_sync"):
            with httpx.stream("GET", "http://example.com/sse", timeout=2.0) as response:
                lines = list(response.iter_lines())
                with pytest.raises(httpx.StreamConsumed):
                    list(response.iter_lines())

    assert response.status_code == 200
    assert lines == ["data: first", "", "data: second", ""]


@pytest.mark.asyncio
async def test_streaming_replay_iter_lines_async(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag="sse_async",
                uri="http://example.com/sse-async",
                body=_sse_body(),
                content_type="text/event-stream",
            ),
        ],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    async with httpx.AsyncClient(timeout=2.0) as client:
        with interceptor.use_cassette():
            with invocation_context("sse_async"):
                async with client.stream("GET", "http://example.com/sse-async") as response:
                    lines: list[str] = [line async for line in response.aiter_lines()]
                    with pytest.raises(httpx.StreamConsumed):
                        _ = [line async for line in response.aiter_lines()]

    assert response.status_code == 200
    assert lines == ["data: first", "", "data: second", ""]
