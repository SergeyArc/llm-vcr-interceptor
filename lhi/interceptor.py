from __future__ import annotations

import atexit
import hashlib
import inspect
import json
import logging
import os
import re
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import vcr
import yaml
from vcr.request import Request as VcrRequest

from lhi.context import get_current_invocation_tag
from lhi.scenario import ScenarioRow
from lhi.session import AddRecords, AddSession, RemoveRecords, Session
from lhi.streaming import apply_replay_streaming_shim, normalize_streaming_response

INVOCATION_TAG_HEADER = "x-invocation-tag"
type IdentityStrategy = Literal["fingerprint", "callsite", "explicit_first"]
DEFAULT_CALLSITE_SKIP_PREFIXES: tuple[str, ...] = (
    "lhi.",
    "vcr.",
    "httpx.",
    "httpcore.",
    "anthropic.",
    "openai.",
    "asyncio.",
    "concurrent.",
    # stdlib module name has no package prefix.
    "contextlib",
)
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


def _make_request_identity_matcher(scenario: ScenarioRow | None) -> Any:
    def lhi_request_identity_matcher(r1: Any, r2: Any) -> None:
        incoming_tag = _header_first(r1, INVOCATION_TAG_HEADER)
        stored_tag = _header_first(r2, INVOCATION_TAG_HEADER)
        if incoming_tag:
            if scenario is not None and scenario.invocation_patch_regexps:
                if not any(re.search(pattern, incoming_tag) for pattern in scenario.invocation_patch_regexps):
                    raise AssertionError(
                        f"invocation_tag {incoming_tag!r} does not match scenario {scenario.name!r} -> live",
                    )
            if not stored_tag:
                raise AssertionError("cassette record is missing X-Invocation-Tag")
            if incoming_tag != stored_tag:
                raise AssertionError(f"cassette tag {stored_tag!r} != current tag {incoming_tag!r}")
            return

        incoming_fingerprint = _build_request_fingerprint(getattr(r1, "body", None))
        stored_fingerprint = _build_request_fingerprint(getattr(r2, "body", None))
        if incoming_fingerprint != stored_fingerprint:
            raise AssertionError(
                "request body fingerprint mismatch; prompt or generation parameters changed; "
                "re-record cassette with record_mode='new_episodes'",
            )

    return lhi_request_identity_matcher


def _body_to_bytes(body: Any) -> bytes:
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return str(body).encode("utf-8")


def _canonicalize_request_body(body: Any) -> bytes:
    payload = _body_to_bytes(body)
    if not payload:
        return payload
    try:
        decoded = payload.decode("utf-8")
        parsed = json.loads(decoded)
        normalized = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return normalized.encode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return payload


def _build_request_fingerprint(body: Any) -> str:
    canonical_body = _canonicalize_request_body(body)
    digest = hashlib.sha256(canonical_body).hexdigest()
    return f"sha256:{digest}"


def _canonicalize_json_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _build_messages_fingerprint(body: Any) -> str:
    payload = _body_to_bytes(body)
    if not payload:
        return hashlib.sha256(b"").hexdigest()
    try:
        decoded = payload.decode("utf-8")
        parsed = json.loads(decoded)
        if not isinstance(parsed, dict):
            return hashlib.sha256(_canonicalize_request_body(body)).hexdigest()
        prompt_payload = {
            "system": parsed.get("system"),
            "messages": parsed.get("messages"),
        }
        canonical = _canonicalize_json_value(prompt_payload).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return hashlib.sha256(_canonicalize_request_body(body)).hexdigest()


def _resolve_project_root(callsite_project_root: str | None) -> Path:
    if callsite_project_root:
        return Path(callsite_project_root).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return current


def _find_app_frame(skip_prefixes: tuple[str, ...]) -> tuple[str, str] | None:
    frame = inspect.currentframe()
    if frame is None:
        return None
    try:
        current = frame.f_back
        while current is not None:
            module_name = str(current.f_globals.get("__name__", ""))
            if not any(module_name.startswith(prefix) for prefix in skip_prefixes):
                return current.f_code.co_filename, current.f_code.co_name
            current = current.f_back
        return None
    finally:
        del frame


def _derive_callsite_tag(
    body: Any,
    *,
    skip_prefixes: tuple[str, ...],
    project_root: Path,
) -> str:
    app_frame = _find_app_frame(skip_prefixes)
    if app_frame is None:
        return ""
    frame_filename, frame_function = app_frame
    frame_path = Path(frame_filename)
    try:
        relative_file = frame_path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        relative_file = frame_path.name
    if relative_file.startswith("<"):
        return ""
    messages_hash8 = _build_messages_fingerprint(body)[:8]
    return f"callsite:{relative_file}:{frame_function}:{messages_hash8}"


def _copy_request_with_header(request: Any, header_name: str, header_value: str) -> Any:
    headers = dict(getattr(request, "headers", {}))
    headers[header_name] = header_value
    return VcrRequest(
        getattr(request, "method"),
        getattr(request, "uri"),
        getattr(request, "body", None),
        headers,
    )


def _is_loading_cassette() -> bool:
    frame = inspect.currentframe()
    if frame is None:
        return False
    try:
        current = frame.f_back
        while current is not None:
            if current.f_globals.get("__name__") == "vcr.cassette" and current.f_code.co_name == "_load":
                return True
            current = current.f_back
        return False
    finally:
        del frame


def _make_before_record_request_hook(
    *,
    scenario: ScenarioRow | None,
    record_mode: str,
    identity_strategy: IdentityStrategy,
    callsite_skip_prefixes: tuple[str, ...],
    callsite_project_root: str | None,
) -> Any:
    project_root = _resolve_project_root(callsite_project_root)

    def _inject_invocation_tag_header(request: Any) -> Any:
        existing_tag = _header_first(request, INVOCATION_TAG_HEADER)
        if existing_tag:
            return request
        tag = get_current_invocation_tag() or ""
        if not tag and identity_strategy in ("callsite", "explicit_first"):
            if _is_loading_cassette():
                return request
            tag = _derive_callsite_tag(
                getattr(request, "body", None),
                skip_prefixes=callsite_skip_prefixes,
                project_root=project_root,
            )
            if not tag and identity_strategy == "callsite":
                logging.warning(
                    "lhi: identity_strategy='callsite' could not derive app frame; "
                    "falling back to fingerprint matching",
                )
        if tag:
            request_with_tag = _copy_request_with_header(request, INVOCATION_TAG_HEADER, tag)
            if record_mode != "none" and scenario is not None and scenario.invocation_patch_regexps:
                if not any(re.search(pattern, tag) for pattern in scenario.invocation_patch_regexps):
                    return None
            return request_with_tag
        return request

    return _inject_invocation_tag_header


@contextmanager
def _httpcore_replay_shim() -> Iterator[None]:
    import vcr.stubs.httpcore_stubs as httpcore_stubs  # type: ignore[import-untyped]

    original_play_responses = httpcore_stubs._play_responses
    deserialize_response = httpcore_stubs._deserialize_response

    def _play_responses_with_shim(cassette: Any, vcr_request: Any) -> Any:
        vcr_response = cassette.play_response(vcr_request)
        real_response = deserialize_response(vcr_response)
        return apply_replay_streaming_shim(vcr_response, real_response)

    httpcore_stubs._play_responses = _play_responses_with_shim
    try:
        yield
    finally:
        httpcore_stubs._play_responses = original_play_responses


class LHIInterceptor:
    """Interceptor with tag-aware and body-fingerprint-aware VCR matcher."""

    def __init__(
        self,
        sessions: Mapping[int, str] | Sequence[Session],
        scenario: ScenarioRow | None = None,
        *,
        cassette_library_dir: str | None = None,
        record_mode: str | None = None,
        identity_strategy: IdentityStrategy = "fingerprint",
        callsite_skip_prefixes: tuple[str, ...] = DEFAULT_CALLSITE_SKIP_PREFIXES,
        callsite_project_root: str | None = None,
    ) -> None:
        self._sessions = _normalize_sessions(sessions)
        self._scenario = scenario
        self._base_library_dir = cassette_library_dir or os.environ.get(
            "VCR_CASSETTES_DIR",
            "cassettes",
        )
        self._record_mode = record_mode or os.environ.get("VCR_RECORD_MODE", "new_episodes")
        self._identity_strategy = identity_strategy
        self._callsite_skip_prefixes = callsite_skip_prefixes
        self._callsite_project_root = callsite_project_root
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
        before_record_request_hook = _make_before_record_request_hook(
            scenario=self._scenario,
            record_mode=self._record_mode,
            identity_strategy=self._identity_strategy,
            callsite_skip_prefixes=self._callsite_skip_prefixes,
            callsite_project_root=self._callsite_project_root,
        )
        instance = vcr.VCR(
            cassette_library_dir=self._cassette_library_dir,
            record_mode=self._record_mode,
            before_record_request=before_record_request_hook,
            before_record_response=normalize_streaming_response,
            # In record_mode="all", old interactions are never replayed.
            # Dropping unused requests makes saves overwrite previous runs instead of appending.
            drop_unused_requests=self._record_mode == "all",
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
                "lhi_request_identity",
            ),
        )
        instance.register_matcher(
            "lhi_request_identity",
            _make_request_identity_matcher(self._scenario),
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

    def _reset_primary_cassette_for_record_all(self) -> None:
        if self._record_mode != "all" or self._virtual_cassette_path:
            return
        primary_rel = self._sessions[self._primary_session_id]
        primary_path = Path(self._base_library_dir) / primary_rel
        primary_path.unlink(missing_ok=True)

    @contextmanager
    def use_cassette(self) -> Iterator[None]:
        previous_count = 0
        self._reset_primary_cassette_for_record_all()
        if self._virtual_cassette_path:
            previous_count = len(
                _load_cassette_document(Path(self._virtual_cassette_path)).get("interactions") or [],
            )
        try:
            with _httpcore_replay_shim(), self._vcr.use_cassette(self._cassette_name):
                yield
        finally:
            if self._virtual_cassette_path:
                self._sync_new_interactions_to_primary(previous_count)
            elif self._record_mode != "none":
                self._update_primary_recorded_at()
