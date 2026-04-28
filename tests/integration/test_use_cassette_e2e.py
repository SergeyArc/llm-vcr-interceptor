from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from vcr.errors import CannotOverwriteExistingCassetteException

from lhi import LHIInterceptor


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
