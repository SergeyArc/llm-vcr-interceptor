from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from vcr.errors import CannotOverwriteExistingCassetteException

from lhi import LHIInterceptor
from lhi.context import invocation_context
from lhi.interceptor import DEFAULT_CALLSITE_SKIP_PREFIXES, _derive_callsite_tag


def _send_loop_request(
    url: str,
    payload: dict[str, Any],
    *,
    derive_only: bool = False,
    callsite_skip_prefixes: tuple[str, ...],
) -> str | httpx.Response:
    derived_tag = _derive_callsite_tag(
        json.dumps(payload),
        skip_prefixes=callsite_skip_prefixes,
        project_root=Path.cwd(),
    )
    if derive_only:
        return derived_tag
    return httpx.post(url, json=payload, timeout=2.0)


def test_use_cassette_replays_response_from_yaml_without_network(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    tagged_get_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag="actor_model_def",
                uri="http://example.com/answer",
                body='{"answer":"from cassette"}',
            ),
        ],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        response = tagged_get_fixture("http://example.com/answer", "actor_model_def")
    assert response.status_code == 200
    assert '"answer":"from cassette"' in response.text


def test_use_cassette_replay_none_fails_for_missing_tag(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    tagged_get_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [make_interaction_fixture(invocation_tag="known_tag", uri="http://example.com/missing")],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        with pytest.raises(CannotOverwriteExistingCassetteException):
            tagged_get_fixture("http://example.com/missing", "unknown_tag")


def test_use_cassette_replays_response_by_body_without_invocation_tag(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    untagged_post_json_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag=None,
                uri="http://example.com/replay-by-body",
                method="POST",
                request_body='{"temperature":0.7,"messages":[{"content":"Hello","role":"user"}]}',
                body='{"answer":"body replay"}',
            ),
        ],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        response = untagged_post_json_fixture(
            "http://example.com/replay-by-body",
            {"messages": [{"role": "user", "content": "Hello"}], "temperature": 0.7},
        )
    assert response.status_code == 200
    assert '"answer":"body replay"' in response.text


def test_use_cassette_replay_none_reports_body_fingerprint_mismatch(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    untagged_post_json_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag=None,
                uri="http://example.com/mismatch",
                method="POST",
                request_body='{"messages":[{"content":"A","role":"user"}],"temperature":0.7}',
            ),
        ],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        with pytest.raises(
            CannotOverwriteExistingCassetteException,
            match="prompt or generation parameters changed",
        ):
            untagged_post_json_fixture(
                "http://example.com/mismatch",
                {"messages": [{"role": "user", "content": "A"}], "temperature": 0.0},
            )


def test_callsite_strategy_replays_without_invocation_context(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
) -> None:
    payload = {
        "system": "math tutor",
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "temperature": 0.7,
    }
    callsite_skip_prefixes = (*DEFAULT_CALLSITE_SKIP_PREFIXES, "tests.conftest")
    derived_tag = _derive_callsite_tag(
        json.dumps(payload),
        skip_prefixes=callsite_skip_prefixes,
        project_root=Path.cwd(),
    )
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag=derived_tag,
                method="POST",
                uri="http://example.com/callsite",
                body='{"answer":"callsite replay"}',
            ),
        ],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
        identity_strategy="callsite",
        callsite_skip_prefixes=callsite_skip_prefixes,
        callsite_project_root=str(Path.cwd()),
    )

    with interceptor.use_cassette():
        response = httpx.post("http://example.com/callsite", json=payload, timeout=2.0)
    assert response.status_code == 200
    assert '"answer":"callsite replay"' in response.text


def test_callsite_strategy_supports_scenario_row_without_explicit_tags(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
) -> None:
    callsite_skip_prefixes = (*DEFAULT_CALLSITE_SKIP_PREFIXES, "tests.conftest")

    def callsite_math(*, derive_only: bool = False) -> str | httpx.Response:
        payload = {"messages": [{"role": "user", "content": "What is 5 + 7?"}]}
        tag = _derive_callsite_tag(
            json.dumps(payload),
            skip_prefixes=callsite_skip_prefixes,
            project_root=Path.cwd(),
        )
        if derive_only:
            return tag
        return httpx.post("http://example.com/partial", json=payload, timeout=2.0)

    def callsite_general(*, derive_only: bool = False) -> str | httpx.Response:
        payload = {"messages": [{"role": "user", "content": "What is the capital of France?"}]}
        tag = _derive_callsite_tag(
            json.dumps(payload),
            skip_prefixes=callsite_skip_prefixes,
            project_root=Path.cwd(),
        )
        if derive_only:
            return tag
        return httpx.post("http://example.com/partial", json=payload, timeout=2.0)

    math_tag = callsite_math(derive_only=True)
    general_tag = callsite_general(derive_only=True)
    assert isinstance(math_tag, str)
    assert isinstance(general_tag, str)
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag=math_tag,
                method="POST",
                uri="http://example.com/partial",
                body='{"answer":"math replay"}',
            ),
            make_interaction_fixture(
                invocation_tag=general_tag,
                method="POST",
                uri="http://example.com/partial",
                body='{"answer":"general replay"}',
            ),
        ],
    )
    from lhi import ScenarioRow

    scenario = ScenarioRow(
        name="math_only",
        invocation_patch_regexps=(r"callsite:.*:callsite_math:.*",),
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
        scenario=scenario,
        identity_strategy="callsite",
        callsite_skip_prefixes=callsite_skip_prefixes,
        callsite_project_root=str(Path.cwd()),
    )

    with interceptor.use_cassette():
        math_response = callsite_math()
        assert isinstance(math_response, httpx.Response)
        assert '"answer":"math replay"' in math_response.text
        with pytest.raises(CannotOverwriteExistingCassetteException):
            callsite_general()


def test_explicit_first_strategy_prioritizes_invocation_context(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag="explicit_tag",
                method="POST",
                uri="http://example.com/explicit-first",
                body='{"answer":"explicit"}',
            ),
        ],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
        identity_strategy="explicit_first",
        callsite_project_root=str(Path.cwd()),
    )

    with interceptor.use_cassette():
        with invocation_context("explicit_tag"):
            response = httpx.post(
                "http://example.com/explicit-first",
                json={"messages": [{"role": "user", "content": "ignored by explicit tag"}]},
                timeout=2.0,
            )
    assert response.status_code == 200
    assert '"answer":"explicit"' in response.text


def test_callsite_loop_with_different_prompts_produces_independent_replays(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
) -> None:
    callsite_skip_prefixes = (*DEFAULT_CALLSITE_SKIP_PREFIXES, "tests.conftest")
    payload_first = {"messages": [{"role": "user", "content": "2+2?"}]}
    payload_second = {"messages": [{"role": "user", "content": "capital of France?"}]}
    first_tag = _send_loop_request(
        "http://example.com/loop",
        payload_first,
        derive_only=True,
        callsite_skip_prefixes=callsite_skip_prefixes,
    )
    second_tag = _send_loop_request(
        "http://example.com/loop",
        payload_second,
        derive_only=True,
        callsite_skip_prefixes=callsite_skip_prefixes,
    )
    assert isinstance(first_tag, str)
    assert isinstance(second_tag, str)
    assert first_tag != second_tag

    write_cassette_fixture(
        tmp_path / "session.yaml",
        [
            make_interaction_fixture(
                invocation_tag=first_tag,
                method="POST",
                uri="http://example.com/loop",
                body='{"answer":"four"}',
            ),
            make_interaction_fixture(
                invocation_tag=second_tag,
                method="POST",
                uri="http://example.com/loop",
                body='{"answer":"paris"}',
            ),
        ],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
        identity_strategy="callsite",
        callsite_skip_prefixes=callsite_skip_prefixes,
        callsite_project_root=str(Path.cwd()),
    )

    with interceptor.use_cassette():
        first_response = _send_loop_request(
            "http://example.com/loop",
            payload_first,
            callsite_skip_prefixes=callsite_skip_prefixes,
        )
        second_response = _send_loop_request(
            "http://example.com/loop",
            payload_second,
            callsite_skip_prefixes=callsite_skip_prefixes,
        )
    assert isinstance(first_response, httpx.Response)
    assert isinstance(second_response, httpx.Response)
    assert '"answer":"four"' in first_response.text
    assert '"answer":"paris"' in second_response.text


def test_callsite_same_prompt_produces_same_tag() -> None:
    callsite_skip_prefixes = (*DEFAULT_CALLSITE_SKIP_PREFIXES, "tests.conftest")
    payload = {"messages": [{"role": "user", "content": "repeat prompt"}]}
    first_tag = _send_loop_request(
        "http://example.com/repeat",
        payload,
        derive_only=True,
        callsite_skip_prefixes=callsite_skip_prefixes,
    )
    second_tag = _send_loop_request(
        "http://example.com/repeat",
        payload,
        derive_only=True,
        callsite_skip_prefixes=callsite_skip_prefixes,
    )
    assert isinstance(first_tag, str)
    assert isinstance(second_tag, str)
    assert first_tag == second_tag
