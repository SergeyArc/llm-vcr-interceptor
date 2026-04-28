from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from vcr.errors import CannotOverwriteExistingCassetteException

from lhi import LHIInterceptor, ScenarioRow
from lhi.session import AddSession, RemoveRecords


def test_merge_overwrite_by_tag_prefers_added_session(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    tagged_get_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "primary.yaml",
        [make_interaction_fixture(invocation_tag="tag-1", uri="http://example.com/merge", body='{"source":"primary"}')],
    )
    write_cassette_fixture(
        tmp_path / "extra.yaml",
        [make_interaction_fixture(invocation_tag="tag-1", uri="http://example.com/merge", body='{"source":"extra"}')],
    )
    scenario = ScenarioRow(
        name="merge_overwrite",
        invocation_patch_regexps=(),
        edits=(AddSession(session_id=0), AddSession(session_id=1)),
    )
    interceptor = LHIInterceptor(
        sessions={0: "primary.yaml", 1: "extra.yaml"},
        scenario=scenario,
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        response = tagged_get_fixture("http://example.com/merge", "tag-1")
    assert response.status_code == 200
    assert '"source":"extra"' in response.text


def test_merge_remove_records_excludes_matching_tags(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    tagged_get_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "primary.yaml",
        [
            make_interaction_fixture(invocation_tag="remove_me", uri="http://example.com/remove"),
            make_interaction_fixture(invocation_tag="keep_me", uri="http://example.com/keep", body='{"source":"keep"}'),
        ],
    )
    scenario = ScenarioRow(
        name="remove_paths",
        invocation_patch_regexps=(),
        edits=(AddSession(session_id=0), RemoveRecords(tags=("remove_.*",))),
    )
    interceptor = LHIInterceptor(
        sessions={0: "primary.yaml"},
        scenario=scenario,
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        with pytest.raises(CannotOverwriteExistingCassetteException):
            tagged_get_fixture("http://example.com/remove", "remove_me")
        kept = tagged_get_fixture("http://example.com/keep", "keep_me")
    assert kept.status_code == 200


def test_scenario_regex_patch_rejects_non_matching_invocation_tag(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    tagged_get_fixture: Any,
) -> None:
    write_cassette_fixture(
        tmp_path / "session.yaml",
        [make_interaction_fixture(invocation_tag="general_q", uri="http://example.com/general")],
    )
    scenario = ScenarioRow(
        name="math_only",
        invocation_patch_regexps=(r"^math_.*",),
        edits=(),
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        scenario=scenario,
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        with pytest.raises(Exception, match="does not match scenario"):
            tagged_get_fixture("http://example.com/general", "general_q")
