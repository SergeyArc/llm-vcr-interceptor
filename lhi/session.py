from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Session:
    """Именованная сессия записей (файл кассеты VCR)."""

    session_id: int
    cassette_path: str


@dataclass(frozen=True, slots=True)
class AddSession:
    """Правка сценария: подключить сессию по идентификатору."""

    session_id: int
