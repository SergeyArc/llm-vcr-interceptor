from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lhi.interceptor import (
    DEFAULT_CALLSITE_SKIP_PREFIXES,
    INVOCATION_TAG_HEADER,
    _build_messages_fingerprint,
    _build_request_fingerprint,
    _canonicalize_request_body,
    _collect_remove_patterns,
    _derive_callsite_tag,
    _header_first,
    _interaction_matches_any_tag,
    _make_before_record_request_hook,
    _invocation_tag_from_interaction,
    _load_cassette_document,
    _needs_virtual_merge,
    _resolve_primary_session_id,
    _tag_matches_selector,
    _write_cassette_document,
)
from lhi.scenario import ScenarioRow
from lhi.session import AddRecords, AddSession, RemoveRecords


def test_header_first_missing_attribute_returns_empty() -> None:
    class Request:
        pass

    assert _header_first(Request(), "x-foo") == ""


def test_header_first_string_and_list_values() -> None:
    class Request:
        headers = {"X-Foo": "bar", "X-List": ["a", "b"]}

    assert _header_first(Request(), "X-Foo") == "bar"
    assert _header_first(Request(), "X-List") == "a"
    assert _header_first(Request(), "X-Missing") == ""


def test_invocation_tag_from_interaction_variants() -> None:
    interaction_no_headers: dict[str, Any] = {"request": {}}
    interaction_str = {"request": {"headers": {"X-Invocation-Tag": "tag-a"}}}
    interaction_list = {"request": {"headers": {INVOCATION_TAG_HEADER: ["first", "second"]}}}

    assert _invocation_tag_from_interaction(interaction_no_headers) == ""
    assert _invocation_tag_from_interaction(interaction_str) == "tag-a"
    assert _invocation_tag_from_interaction(interaction_list) == "first"


def test_tag_matches_selector_supports_exact_and_regex() -> None:
    assert _tag_matches_selector("abc", "abc") is True
    assert _tag_matches_selector("actor_1", r"actor_\d+") is True
    assert _tag_matches_selector("other", r"actor_\d+") is False
    assert _tag_matches_selector("x", "(") is False


def test_interaction_matches_any_tag() -> None:
    interaction = {"request": {"headers": {INVOCATION_TAG_HEADER: "match_me"}}}
    assert _interaction_matches_any_tag(interaction, ("other", "match_me")) is True
    assert _interaction_matches_any_tag(interaction, ("a", "b")) is False


def test_collect_remove_patterns_from_scenario() -> None:
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


def test_needs_virtual_merge() -> None:
    assert _needs_virtual_merge(None) is False
    assert _needs_virtual_merge(ScenarioRow(name="s", invocation_patch_regexps=(), edits=())) is False
    assert _needs_virtual_merge(
        ScenarioRow(
            name="s",
            invocation_patch_regexps=(),
            edits=(AddRecords(session_id=1, tags=("t",)),),
        ),
    ) is True


def test_resolve_primary_session_id_rules() -> None:
    empty_scenario = ScenarioRow(name="s", invocation_patch_regexps=(), edits=())
    scenario_from_add = ScenarioRow(
        name="s",
        invocation_patch_regexps=(),
        edits=(AddSession(session_id=7), AddSession(session_id=9)),
    )
    scenario_from_records = ScenarioRow(
        name="s",
        invocation_patch_regexps=(),
        edits=(AddRecords(session_id=3, tags=("t",)),),
    )
    assert _resolve_primary_session_id(scenario_from_add, {1: "a.yaml", 7: "b.yaml"}) == 7
    assert _resolve_primary_session_id(scenario_from_records, {1: "a.yaml", 3: "b.yaml"}) == 3
    assert _resolve_primary_session_id(empty_scenario, {5: "a", 2: "b"}) == 2
    with pytest.raises(ValueError, match="sessions is empty"):
        _resolve_primary_session_id(empty_scenario, {})


def test_load_cassette_document_invalid_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- not: a mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid cassette YAML format"):
        _load_cassette_document(path)


def test_write_and_load_cassette_document_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cassette.yaml"
    interactions: list[dict[str, Any]] = [{"request": {"headers": {INVOCATION_TAG_HEADER: "t1"}}}]
    _write_cassette_document(path, interactions, recorded_at="2026-04-28T07:00:00+00:00")
    loaded = _load_cassette_document(path)
    assert loaded["version"] == 1
    assert loaded["recorded_at"] == "2026-04-28T07:00:00+00:00"
    assert _invocation_tag_from_interaction(loaded["interactions"][0]) == "t1"


def test_canonicalize_request_body_sorts_json_keys() -> None:
    first = _canonicalize_request_body('{"b":2,"a":1}')
    second = _canonicalize_request_body('{"a":1,"b":2}')
    assert first == second


def test_build_request_fingerprint_is_stable_for_equivalent_json() -> None:
    first = _build_request_fingerprint('{"messages":[{"role":"user","content":"hello"}],"temperature":0.7}')
    second = _build_request_fingerprint('{"temperature":0.7,"messages":[{"content":"hello","role":"user"}]}')
    assert first == second


def test_build_request_fingerprint_changes_when_payload_changes() -> None:
    first = _build_request_fingerprint('{"temperature":0.7,"messages":[{"content":"hello"}]}')
    second = _build_request_fingerprint('{"temperature":0.0,"messages":[{"content":"hello"}]}')
    assert first != second


def test_build_messages_fingerprint_uses_system_and_messages() -> None:
    first = _build_messages_fingerprint(
        '{"system":"math tutor","messages":[{"role":"user","content":"2+2?"}],"temperature":0.7}',
    )
    second = _build_messages_fingerprint(
        '{"system":"math tutor","messages":[{"content":"2+2?","role":"user"}],"temperature":0.0}',
    )
    third = _build_messages_fingerprint(
        '{"system":"history tutor","messages":[{"role":"user","content":"2+2?"}],"temperature":0.7}',
    )
    assert first == second
    assert first != third


def test_make_before_record_request_hook_idempotent_when_tag_exists() -> None:
    class Request:
        body = b'{"messages":[{"role":"user","content":"hello"}]}'
        headers = {INVOCATION_TAG_HEADER: "existing"}

    hook = _make_before_record_request_hook(
        identity_strategy="callsite",
        callsite_skip_prefixes=DEFAULT_CALLSITE_SKIP_PREFIXES,
        callsite_project_root=str(Path.cwd()),
    )
    result = hook(Request())
    assert result.headers[INVOCATION_TAG_HEADER] == "existing"


def test_derive_callsite_tag_returns_empty_when_no_app_frame() -> None:
    tag = _derive_callsite_tag(
        '{"messages":[{"role":"user","content":"hello"}]}',
        skip_prefixes=("",),
        project_root=Path.cwd(),
    )
    assert tag == ""
