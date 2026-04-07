from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

import vcr

from lhi.scenario import ScenarioRow

INVOCATION_TAG_HEADER = "x-invocation-tag"

_current_tag: ContextVar[str | None] = ContextVar("lhi_tag", default=None)


def get_current_invocation_tag() -> str | None:
    return _current_tag.get()


def _header_first(request: Any, name: str) -> str:
    headers = getattr(request, "headers", {})
    value = headers.get(name)
    if value is None:
        return ""
    if isinstance(value, list):
        return value[0] if value else ""
    return str(value)


def _make_invocation_tag_matcher(scenario: ScenarioRow | None) -> Any:
    def lhi_invocation_tag_matcher(r1: Any, r2: Any) -> None:
        incoming = _header_first(r1, INVOCATION_TAG_HEADER) or (_current_tag.get() or "")
        stored = _header_first(r2, INVOCATION_TAG_HEADER)
        if scenario is not None and scenario.invocation_patch_regexps:
            if not any(re.search(pattern, incoming) for pattern in scenario.invocation_patch_regexps):
                raise AssertionError(
                    f"invocation_tag {incoming!r} не попадает под сценарий {scenario.name!r} → live",
                )
        if not incoming:
            raise AssertionError("нет invocation_tag")
        if not stored:
            raise AssertionError("в кассете нет X-Invocation-Tag")
        if incoming != stored:
            raise AssertionError(f"тег кассеты {stored!r} != текущего {incoming!r}")

    return lhi_invocation_tag_matcher


def _inject_invocation_tag_header(request: Any) -> Any:
    tag = _current_tag.get()
    if tag:
        request.headers[INVOCATION_TAG_HEADER] = tag
    return request


class LHIInterceptor:
    """Перехватчик: invocation_tag в ContextVar + VCR-матчер по заголовку X-Invocation-Tag."""

    def __init__(
        self,
        sessions: dict[int, str],
        scenario: ScenarioRow | None = None,
        *,
        cassette_library_dir: str | None = None,
        record_mode: str | None = None,
    ) -> None:
        self._sessions = dict(sessions)
        self._scenario = scenario
        self._cassette_library_dir = cassette_library_dir or os.environ.get(
            "VCR_CASSETTES_DIR",
            "cassettes",
        )
        self._record_mode = record_mode or os.environ.get("VCR_RECORD_MODE", "new_episodes")
        self._vcr = self._build_vcr()
        self._cassette_name = self._resolve_cassette_name()

    def _resolve_cassette_name(self) -> str:
        if self._scenario is not None and self._scenario.edits:
            primary = self._scenario.edits[0].session_id
        else:
            primary = min(self._sessions.keys(), default=0)
        if primary not in self._sessions:
            msg = f"Нет пути кассеты для session_id={primary}"
            raise KeyError(msg)
        return self._sessions[primary]

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
        instance.register_matcher("lhi_invocation_tag", _make_invocation_tag_matcher(self._scenario))
        return instance

    @property
    def vcr(self) -> vcr.VCR:
        return self._vcr

    @property
    def cassette_name(self) -> str:
        return self._cassette_name

    @contextmanager
    def use_cassette(self) -> Iterator[None]:
        with self._vcr.use_cassette(self._cassette_name):
            yield

    async def generate(self, service: Any, prompt: str, invocation_tag: str) -> str:
        token = _current_tag.set(invocation_tag)
        try:
            return await service.generate(prompt)
        finally:
            _current_tag.reset(token)
