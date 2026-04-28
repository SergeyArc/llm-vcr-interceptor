from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from lhi import interceptor as interceptor_module
from lhi.context import get_current_invocation_tag, invocation_context
from lhi.interceptor import (
    INVOCATION_TAG_HEADER,
    LHIInterceptor,
    _collect_remove_patterns,
    _header_first,
    _interaction_matches_any_tag,
    _invocation_tag_from_interaction,
    _load_cassette_document,
    _needs_virtual_merge,
    _resolve_primary_session_id,
    _tag_matches_selector,
    _write_cassette_document,
)
from lhi.scenario import ScenarioRow
from lhi.session import AddRecords, AddSession, RemoveRecords, Session


def test_header_first_missing_attribute_returns_empty() -> None:
    class Request:
        pass

    assert _header_first(Request(), "x-foo") == ""


def test_header_first_missing_key_returns_empty() -> None:
    class Request:
        headers: dict[str, str] = {}

    assert _header_first(Request(), "x-foo") == ""


def test_header_first_string_value() -> None:
    class Request:
        headers = {"X-Foo": "bar"}

    assert _header_first(Request(), "X-Foo") == "bar"


def test_header_first_list_value() -> None:
    class Request:
        headers = {"X-Foo": ["a", "b"]}

    assert _header_first(Request(), "X-Foo") == "a"


def test_header_first_empty_list_returns_empty() -> None:
    class Request:
        headers = {"X-Foo": []}

    assert _header_first(Request(), "X-Foo") == ""


def test_invocation_tag_from_interaction_no_headers() -> None:
    interaction: dict[str, Any] = {"request": {}}
    assert _invocation_tag_from_interaction(interaction) == ""


def test_invocation_tag_from_interaction_case_insensitive_header() -> None:
    interaction = {
        "request": {
            "headers": {"X-Invocation-Tag": "tag-a"},
        },
    }
    assert _invocation_tag_from_interaction(interaction) == "tag-a"


def test_invocation_tag_from_interaction_list_header_value() -> None:
    interaction = {
        "request": {
            "headers": {INVOCATION_TAG_HEADER: ["first", "second"]},
        },
    }
    assert _invocation_tag_from_interaction(interaction) == "first"


def test_tag_matches_selector_exact() -> None:
    assert _tag_matches_selector("abc", "abc") is True
    assert _tag_matches_selector("abc", "ab") is False


def test_tag_matches_selector_regex() -> None:
    assert _tag_matches_selector("actor_1", r"actor_\d+") is True
    assert _tag_matches_selector("other", r"actor_\d+") is False


def test_tag_matches_selector_invalid_regex_returns_false() -> None:
    assert _tag_matches_selector("x", "(") is False


def test_interaction_matches_any_tag_no_stored_tag() -> None:
    interaction = {"request": {"headers": {}}}
    assert _interaction_matches_any_tag(interaction, ("a",)) is False


def test_interaction_matches_any_tag_matches() -> None:
    interaction = {
        "request": {"headers": {INVOCATION_TAG_HEADER: "match_me"}},
    }
    assert _interaction_matches_any_tag(interaction, ("other", "match_me")) is True


def test_interaction_matches_any_tag_no_match() -> None:
    interaction = {
        "request": {"headers": {INVOCATION_TAG_HEADER: "only"}},
    }
    assert _interaction_matches_any_tag(interaction, ("a", "b")) is False


def test_collect_remove_patterns_empty_edits() -> None:
    scenario = ScenarioRow(name="s", invocation_patch_regexps=(), edits=())
    assert _collect_remove_patterns(scenario) == frozenset()


def test_collect_remove_patterns_mixed_edits() -> None:
    scenario = ScenarioRow(
        name="s",
        invocation_patch_regexps=(),
        edits=(
            AddSession(session_id=1),
            RemoveRecords(tags=("a", "b")),
            AddRecords(session_id=2, tags=("x",)),
        ),
    )
    assert _collect_remove_patterns(scenario) == frozenset({"a", "b"})


def test_needs_virtual_merge_none_scenario() -> None:
    assert _needs_virtual_merge(None) is False


def test_needs_virtual_merge_empty_edits() -> None:
    scenario = ScenarioRow(name="s", invocation_patch_regexps=(), edits=())
    assert _needs_virtual_merge(scenario) is False


def test_needs_virtual_merge_add_session() -> None:
    scenario = ScenarioRow(
        name="s",
        invocation_patch_regexps=(),
        edits=(AddSession(session_id=1),),
    )
    assert _needs_virtual_merge(scenario) is True


def test_needs_virtual_merge_add_records() -> None:
    scenario = ScenarioRow(
        name="s",
        invocation_patch_regexps=(),
        edits=(AddRecords(session_id=1, tags=("t",)),),
    )
    assert _needs_virtual_merge(scenario) is True


def test_needs_virtual_merge_remove_records_only() -> None:
    scenario = ScenarioRow(
        name="s",
        invocation_patch_regexps=(),
        edits=(RemoveRecords(tags=("a",)),),
    )
    assert _needs_virtual_merge(scenario) is True


def test_resolve_primary_session_id_from_add_session() -> None:
    scenario = ScenarioRow(
        name="s",
        invocation_patch_regexps=(),
        edits=(AddSession(session_id=7), AddSession(session_id=9)),
    )
    sessions = {1: "a.yaml", 7: "b.yaml"}
    assert _resolve_primary_session_id(scenario, sessions) == 7


def test_resolve_primary_session_id_from_add_records_when_no_add_session() -> None:
    scenario = ScenarioRow(
        name="s",
        invocation_patch_regexps=(),
        edits=(AddRecords(session_id=3, tags=("t",)),),
    )
    sessions = {1: "a.yaml", 3: "b.yaml"}
    assert _resolve_primary_session_id(scenario, sessions) == 3


def test_resolve_primary_session_id_falls_back_to_min_session_key() -> None:
    scenario = ScenarioRow(name="s", invocation_patch_regexps=(), edits=())
    sessions = {5: "a.yaml", 2: "b.yaml"}
    assert _resolve_primary_session_id(scenario, sessions) == 2


def test_resolve_primary_session_id_empty_sessions_raises() -> None:
    scenario = ScenarioRow(name="s", invocation_patch_regexps=(), edits=())
    with pytest.raises(ValueError, match="sessions is empty"):
        _resolve_primary_session_id(scenario, {})


def test_load_cassette_document_invalid_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- not: a mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid cassette YAML format"):
        _load_cassette_document(path)


def test_write_and_load_cassette_document_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cassette.yaml"
    interactions: list[dict[str, Any]] = [
        {
            "request": {"headers": {INVOCATION_TAG_HEADER: "t1"}},
        },
    ]
    _write_cassette_document(path, interactions)
    loaded = _load_cassette_document(path)
    assert loaded["version"] == 1
    assert len(loaded["interactions"]) == 1
    assert _invocation_tag_from_interaction(loaded["interactions"][0]) == "t1"


def test_write_and_load_cassette_document_with_recorded_at(tmp_path: Path) -> None:
    path = tmp_path / "cassette.yaml"
    interactions: list[dict[str, Any]] = [
        {
            "request": {"headers": {INVOCATION_TAG_HEADER: "t1"}},
        },
    ]
    _write_cassette_document(path, interactions, recorded_at="2026-04-28T07:00:00+00:00")
    loaded = _load_cassette_document(path)
    assert loaded["recorded_at"] == "2026-04-28T07:00:00+00:00"
    assert len(loaded["interactions"]) == 1


def test_sync_to_primary_logs_warning_on_tag_overwrite(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    primary_path = tmp_path / "primary.yaml"
    virtual_path = tmp_path / "virtual.yaml"
    _write_cassette_document(
        primary_path,
        [{"request": {"headers": {INVOCATION_TAG_HEADER: "tag-1"}}, "response": {"status": {"code": 200}}}],
        recorded_at="2026-01-01T00:00:00+00:00",
    )
    _write_cassette_document(
        virtual_path,
        [{"request": {"headers": {INVOCATION_TAG_HEADER: "tag-1"}}, "response": {"status": {"code": 201}}}],
        recorded_at="2026-01-01T00:00:00+00:00",
    )
    interceptor = object.__new__(LHIInterceptor)
    interceptor._virtual_cassette_path = str(virtual_path)
    interceptor._sessions = {0: "primary.yaml"}
    interceptor._primary_session_id = 0
    interceptor._base_library_dir = str(tmp_path)

    with caplog.at_level("WARNING"):
        interceptor._sync_new_interactions_to_primary(previous_count=0)

    assert "overwriting existing cassette interaction for tag 'tag-1'" in caplog.text
    loaded = _load_cassette_document(primary_path)
    assert loaded["interactions"][0]["response"]["status"]["code"] == 201
    assert isinstance(loaded.get("recorded_at"), str)


def test_use_cassette_does_not_update_recorded_at_in_replay_mode_without_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cassette_path = tmp_path / "session.yaml"
    _write_cassette_document(cassette_path, [])
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    @contextmanager
    def fake_use_cassette(_name: str) -> Any:
        yield

    monkeypatch.setattr(interceptor._vcr, "use_cassette", fake_use_cassette)

    with interceptor.use_cassette():
        pass
    loaded = _load_cassette_document(cassette_path)
    assert "recorded_at" not in loaded


def test_use_cassette_updates_recorded_at_each_run_in_recording_mode_without_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cassette_path = tmp_path / "session.yaml"
    _write_cassette_document(cassette_path, [])
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="new_episodes",
    )

    @contextmanager
    def fake_use_cassette(_name: str) -> Any:
        yield

    monkeypatch.setattr(interceptor._vcr, "use_cassette", fake_use_cassette)
    recorded_at_values = iter(("2026-04-28T07:00:00+00:00", "2026-04-28T07:00:01+00:00"))
    monkeypatch.setattr(interceptor_module, "_current_recorded_at", lambda: next(recorded_at_values))

    with interceptor.use_cassette():
        pass
    first_loaded = _load_cassette_document(cassette_path)

    with interceptor.use_cassette():
        pass
    second_loaded = _load_cassette_document(cassette_path)

    assert first_loaded["recorded_at"] == "2026-04-28T07:00:00+00:00"
    assert second_loaded["recorded_at"] == "2026-04-28T07:00:01+00:00"


def test_interceptor_accepts_session_models(tmp_path: Path) -> None:
    _write_cassette_document(tmp_path / "session.yaml", [])
    interceptor = LHIInterceptor(
        sessions=[Session(session_id=0, cassette_path="session.yaml")],
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )
    assert interceptor.cassette_name == "session.yaml"


def test_invocation_context_sets_and_resets_tag() -> None:
    assert get_current_invocation_tag() is None
    with invocation_context("tag-1"):
        assert get_current_invocation_tag() == "tag-1"
    assert get_current_invocation_tag() is None


@pytest.mark.asyncio
async def test_invocation_context_concurrent_tags_are_isolated() -> None:
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


