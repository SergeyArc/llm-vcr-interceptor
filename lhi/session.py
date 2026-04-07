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


@dataclass(frozen=True, slots=True)
class AddRecords:
    """Правка сценария: подключить записи по тегам (точное совпадение или regex)."""

    session_id: int
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RemoveRecords:
    """Правка сценария: удаление существующих записей из кэша для форсирования live-запроса и обновления кассеты."""

    tags: tuple[str, ...]
