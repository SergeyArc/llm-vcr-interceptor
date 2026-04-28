from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_current_invocation_tag: ContextVar[str | None] = ContextVar("lhi_tag", default=None)


def get_current_invocation_tag() -> str | None:
    return _current_invocation_tag.get()


def _set_current_invocation_tag(invocation_tag: str) -> Token[str | None]:
    return _current_invocation_tag.set(invocation_tag)


def _reset_current_invocation_tag(token: Token[str | None]) -> None:
    _current_invocation_tag.reset(token)


@contextmanager
def invocation_context(invocation_tag: str) -> Iterator[None]:
    token = _set_current_invocation_tag(invocation_tag)
    try:
        yield
    finally:
        _reset_current_invocation_tag(token)
