from __future__ import annotations

import atexit
import logging
import os
import re
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import vcr
import yaml

from lhi.context import get_current_invocation_tag
from lhi.scenario import ScenarioRow
from lhi.session import AddRecords, AddSession, RemoveRecords, Session

INVOCATION_TAG_HEADER = "x-invocation-tag"
_virtual_cassette_paths: set[Path] = set()
_virtual_cleanup_registered = False


def _cleanup_virtual_cassettes() -> None:
    for path in tuple(_virtual_cassette_paths):
        path.unlink(missing_ok=True)
    _virtual_cassette_paths.clear()


def _header_first(request: Any, name: str) -> str:
    headers = getattr(request, "headers", {})
    value = headers.get(name)
    if value is None:
        return ""
    if isinstance(value, list):
        return value[0] if value else ""
    return str(value)


def _invocation_tag_from_interaction(interaction: dict[str, Any]) -> str:
    headers = interaction.get("request", {}).get("headers") or {}
    for header_name, raw in headers.items():
        if str(header_name).lower() == INVOCATION_TAG_HEADER.lower():
            if isinstance(raw, list):
                return str(raw[0]) if raw else ""
            return str(raw)
    return ""


def _tag_matches_selector(invocation_tag: str, selector: str) -> bool:
    if invocation_tag == selector:
        return True
    try:
        return re.fullmatch(selector, invocation_tag) is not None
    except re.error:
        return False


def _interaction_matches_any_tag(interaction: dict[str, Any], tags: tuple[str, ...]) -> bool:
    stored = _invocation_tag_from_interaction(interaction)
    if not stored:
        return False
    return any(_tag_matches_selector(stored, pattern) for pattern in tags)


def _collect_remove_patterns(scenario: ScenarioRow) -> frozenset[str]:
    patterns: list[str] = []
    for edit in scenario.edits:
        if isinstance(edit, RemoveRecords):
            patterns.extend(edit.tags)
    return frozenset(patterns)


def _needs_virtual_merge(scenario: ScenarioRow | None) -> bool:
    if scenario is None:
        return False
    return any(isinstance(e, (AddSession, AddRecords, RemoveRecords)) for e in scenario.edits)


def _resolve_primary_session_id(
    scenario: ScenarioRow | None,
    sessions: dict[int, str],
) -> int:
    if scenario and scenario.edits:
        for edit in scenario.edits:
            if isinstance(edit, AddSession):
                return edit.session_id
            if isinstance(edit, AddRecords):
                return edit.session_id
    if sessions:
        return min(sessions.keys())
    msg = "sessions is empty: nothing to replay"
    raise ValueError(msg)


def _normalize_sessions(sessions: Mapping[int, str] | Sequence[Session]) -> dict[int, str]:
    if isinstance(sessions, Mapping):
        return {int(session_id): str(cassette_path) for session_id, cassette_path in sessions.items()}
    return {session.session_id: session.cassette_path for session in sessions}


def _merge_interactions_from_edits(
    scenario: ScenarioRow,
    sessions: dict[int, str],
    base_library_dir: str,
    primary_session_id: int,
    primary_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    merged_by_tag: dict[str, dict[str, Any]] = {}
    for interaction in primary_doc.get("interactions") or []:
        tag = _invocation_tag_from_interaction(interaction)
        if tag:
            merged_by_tag[tag] = interaction

    for edit in scenario.edits:
        if isinstance(edit, RemoveRecords):
            continue
        if isinstance(edit, AddSession):
            path = Path(base_library_dir) / sessions[edit.session_id]
            doc = _load_cassette_document(path)
            batch = list(doc.get("interactions") or [])
        elif isinstance(edit, AddRecords):
            path = Path(base_library_dir) / sessions[edit.session_id]
            doc = _load_cassette_document(path)
            raw = doc.get("interactions") or []
            batch = [i for i in raw if _interaction_matches_any_tag(i, edit.tags)]
        else:
            continue
        for interaction in batch:
            tag = _invocation_tag_from_interaction(interaction)
            if tag:
                merged_by_tag[tag] = interaction

    remove_patterns = _collect_remove_patterns(scenario)
    if remove_patterns:
        for tag in list(merged_by_tag.keys()):
            if any(_tag_matches_selector(tag, pattern) for pattern in remove_patterns):
                del merged_by_tag[tag]

    return list(merged_by_tag.values())


def _load_cassette_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        msg = f"Invalid cassette YAML format: {path}"
        raise ValueError(msg)
    return loaded


def _current_recorded_at() -> str:
    return datetime.now(UTC).isoformat()


def _write_cassette_document(
    path: Path,
    interactions: list[dict[str, Any]],
    *,
    recorded_at: str | None = None,
) -> None:
    payload: dict[str, Any] = {"interactions": interactions, "version": 1}
    if recorded_at is not None:
        payload["recorded_at"] = recorded_at
    path.write_text(yaml.safe_dump(payload, default_flow_style=False, allow_unicode=True), encoding="utf-8")


def _build_virtual_cassette_file(
    scenario: ScenarioRow,
    sessions: dict[int, str],
    base_library_dir: str,
    primary_session_id: int,
) -> str:
    primary_path = Path(base_library_dir) / sessions[primary_session_id]
    primary_doc = _load_cassette_document(primary_path)
    primary_recorded_at = primary_doc.get("recorded_at")
    virtual_recorded_at = primary_recorded_at if isinstance(primary_recorded_at, str) else None
    interactions = _merge_interactions_from_edits(
        scenario,
        sessions,
        base_library_dir,
        primary_session_id,
        primary_doc,
    )
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    try:
        payload: dict[str, Any] = {"interactions": interactions, "version": 1}
        if virtual_recorded_at is not None:
            payload["recorded_at"] = virtual_recorded_at
        yaml.safe_dump(payload, handle, default_flow_style=False, allow_unicode=True)
        handle.close()
    except Exception:
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
        raise
    return handle.name


def _make_invocation_tag_matcher(scenario: ScenarioRow | None) -> Any:
    def lhi_invocation_tag_matcher(r1: Any, r2: Any) -> None:
        incoming = _header_first(r1, INVOCATION_TAG_HEADER) or (get_current_invocation_tag() or "")
        stored = _header_first(r2, INVOCATION_TAG_HEADER)
        if scenario is not None and scenario.invocation_patch_regexps:
            if not any(re.search(pattern, incoming) for pattern in scenario.invocation_patch_regexps):
                raise AssertionError(
                    f"invocation_tag {incoming!r} does not match scenario {scenario.name!r} -> live",
                )
        if not incoming:
            raise AssertionError("missing invocation_tag")
        if not stored:
            raise AssertionError("cassette record is missing X-Invocation-Tag")
        if incoming != stored:
            raise AssertionError(f"cassette tag {stored!r} != current tag {incoming!r}")

    return lhi_invocation_tag_matcher


def _inject_invocation_tag_header(request: Any) -> Any:
    tag = get_current_invocation_tag()
    if tag:
        request.headers[INVOCATION_TAG_HEADER] = tag
    return request


class LHIInterceptor:
    """Interceptor: invocation_tag in ContextVar + VCR matcher by X-Invocation-Tag header."""

    def __init__(
        self,
        sessions: Mapping[int, str] | Sequence[Session],
        scenario: ScenarioRow | None = None,
        *,
        cassette_library_dir: str | None = None,
        record_mode: str | None = None,
    ) -> None:
        self._sessions = _normalize_sessions(sessions)
        self._scenario = scenario
        self._base_library_dir = cassette_library_dir or os.environ.get(
            "VCR_CASSETTES_DIR",
            "cassettes",
        )
        self._record_mode = record_mode or os.environ.get("VCR_RECORD_MODE", "new_episodes")
        self._primary_session_id = _resolve_primary_session_id(scenario, self._sessions)

        if self._primary_session_id not in self._sessions:
            msg = f"Missing cassette path for session_id={self._primary_session_id}"
            raise KeyError(msg)

        self._virtual_cassette_path: str | None = None
        if scenario is not None and _needs_virtual_merge(scenario):
            self._virtual_cassette_path = _build_virtual_cassette_file(
                scenario,
                self._sessions,
                self._base_library_dir,
                self._primary_session_id,
            )
            virtual_path = Path(self._virtual_cassette_path)
            _virtual_cassette_paths.add(virtual_path)
            global _virtual_cleanup_registered
            if not _virtual_cleanup_registered:
                atexit.register(_cleanup_virtual_cassettes)
                _virtual_cleanup_registered = True
            self._cassette_library_dir = str(virtual_path.parent)
            self._cassette_name = virtual_path.name
        else:
            self._cassette_library_dir = self._base_library_dir
            self._cassette_name = self._sessions[self._primary_session_id]

        self._vcr = self._build_vcr()

    def _build_vcr(self) -> vcr.VCR:
        instance = vcr.VCR(
            cassette_library_dir=self._cassette_library_dir,
            record_mode=self._record_mode,
            before_record_request=_inject_invocation_tag_header,
            filter_headers=(
                "authorization",
                "api-key",
                "x-api-key",
            ),
            match_on=(
                "method",
                "scheme",
                "host",
                "port",
                "path",
                "query",
                "lhi_invocation_tag",
            ),
        )
        instance.register_matcher(
            "lhi_invocation_tag",
            _make_invocation_tag_matcher(self._scenario),
        )
        return instance

    @property
    def vcr(self) -> vcr.VCR:
        return self._vcr

    @property
    def cassette_name(self) -> str:
        return self._cassette_name

    def _sync_new_interactions_to_primary(self, previous_count: int) -> None:
        if not self._virtual_cassette_path:
            return
        virtual_path = Path(self._virtual_cassette_path)
        merged_after = _load_cassette_document(virtual_path)
        interactions_after = list(merged_after.get("interactions") or [])
        new_slice = interactions_after[previous_count:]
        if not new_slice:
            return
        primary_rel = self._sessions[self._primary_session_id]
        primary_path = Path(self._base_library_dir) / primary_rel
        primary_doc = _load_cassette_document(primary_path)
        primary_interactions = list(primary_doc.get("interactions") or [])
        primary_by_tag: dict[str, dict[str, Any]] = {}
        primary_untagged: list[dict[str, Any]] = []
        for item in primary_interactions:
            tag = _invocation_tag_from_interaction(item)
            if tag:
                primary_by_tag[tag] = item
            else:
                primary_untagged.append(item)
        for item in new_slice:
            tag = _invocation_tag_from_interaction(item)
            if tag:
                if tag in primary_by_tag:
                    logging.warning(
                        "lhi: overwriting existing cassette interaction for tag %r in %s",
                        tag,
                        primary_path,
                    )
                primary_by_tag[tag] = item
        final_interactions = primary_untagged + list(primary_by_tag.values())
        _write_cassette_document(
            primary_path,
            final_interactions,
            recorded_at=_current_recorded_at(),
        )

    def _update_primary_recorded_at(self) -> None:
        primary_rel = self._sessions[self._primary_session_id]
        primary_path = Path(self._base_library_dir) / primary_rel
        if not primary_path.exists():
            return
        primary_doc = _load_cassette_document(primary_path)
        primary_interactions = list(primary_doc.get("interactions") or [])
        _write_cassette_document(
            primary_path,
            primary_interactions,
            recorded_at=_current_recorded_at(),
        )

    @contextmanager
    def use_cassette(self) -> Iterator[None]:
        previous_count = 0
        if self._virtual_cassette_path:
            previous_count = len(
                _load_cassette_document(Path(self._virtual_cassette_path)).get("interactions") or [],
            )
        try:
            with self._vcr.use_cassette(self._cassette_name):
                yield
        finally:
            if self._virtual_cassette_path:
                self._sync_new_interactions_to_primary(previous_count)
            elif self._record_mode != "none":
                self._update_primary_recorded_at()
