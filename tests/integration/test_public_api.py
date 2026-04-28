from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from lhi import LHIInterceptor, Session, get_current_invocation_tag


def test_interceptor_accepts_session_models(tmp_path: Path, write_cassette_fixture: Any) -> None:
    write_cassette_fixture(tmp_path / "session.yaml", [])
    interceptor = LHIInterceptor(
        sessions=[Session(session_id=0, cassette_path="session.yaml")],
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )
    assert interceptor.cassette_name == "session.yaml"


def test_use_cassette_replay_mode_keeps_recorded_at_unchanged(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    tagged_get_fixture: Any,
    read_cassette_fixture: Any,
) -> None:
    cassette_path = tmp_path / "session.yaml"
    write_cassette_fixture(
        cassette_path,
        [make_interaction_fixture(invocation_tag="tag-1", uri="http://example.com/replay")],
        recorded_at="2026-04-28T07:00:00+00:00",
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        response = tagged_get_fixture("http://example.com/replay", "tag-1")
    assert response.status_code == 200
    assert read_cassette_fixture(cassette_path)["recorded_at"] == "2026-04-28T07:00:00+00:00"


def test_use_cassette_recording_mode_updates_recorded_at(
    tmp_path: Path,
    write_cassette_fixture: Any,
    read_cassette_fixture: Any,
) -> None:
    cassette_path = tmp_path / "session.yaml"
    write_cassette_fixture(cassette_path, [], recorded_at="2026-04-28T07:00:00+00:00")
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="new_episodes",
    )

    with interceptor.use_cassette():
        pass
    first_value = read_cassette_fixture(cassette_path)["recorded_at"]
    with interceptor.use_cassette():
        pass
    second_value = read_cassette_fixture(cassette_path)["recorded_at"]

    assert isinstance(first_value, str)
    assert isinstance(second_value, str)
    assert first_value != "2026-04-28T07:00:00+00:00"
    assert second_value != "2026-04-28T07:00:00+00:00"


def test_invocation_context_sets_and_resets_tag() -> None:
    from lhi import invocation_context

    assert get_current_invocation_tag() is None
    with invocation_context("tag-1"):
        assert get_current_invocation_tag() == "tag-1"
    assert get_current_invocation_tag() is None


@pytest.mark.asyncio
async def test_invocation_context_concurrent_tags_are_isolated() -> None:
    from lhi import invocation_context

    async def read_tag(tag: str, delay: float) -> str | None:
        with invocation_context(tag):
            await asyncio.sleep(delay)
            return get_current_invocation_tag()

    first_tag, second_tag = await asyncio.gather(
        read_tag("alpha", 0.01),
        read_tag("beta", 0.01),
    )
    assert first_tag == "alpha"
    assert second_tag == "beta"
    assert get_current_invocation_tag() is None
