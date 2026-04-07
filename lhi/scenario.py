from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from lhi.session import AddRecords, AddSession, RemoveRecords

EditOperation: TypeAlias = AddSession | AddRecords | RemoveRecords


@dataclass(frozen=True, slots=True)
class ScenarioRow:
    """Именованный набор правил выборочного воспроизведения по invocation_tag."""

    name: str
    invocation_patch_regexps: list[str]
    edits: tuple[EditOperation, ...] = ()
