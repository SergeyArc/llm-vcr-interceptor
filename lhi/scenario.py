from __future__ import annotations

from dataclasses import dataclass

from lhi.session import AddSession


@dataclass(frozen=True, slots=True)
class ScenarioRow:
    """Именованный набор правил выборочного воспроизведения по invocation_tag."""

    name: str
    invocation_patch_regexps: list[str]
    edits: tuple[AddSession, ...] = ()
