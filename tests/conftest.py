from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from lhi.context import invocation_context


def make_http_interaction(
    *,
    invocation_tag: str,
    uri: str,
    method: str = "GET",
    status_code: int = 200,
    body: str = '{"source":"cassette"}',
) -> dict[str, Any]:
    return {
        "request": {
            "body": "",
            "headers": {
                "x-invocation-tag": [invocation_tag],
            },
            "method": method,
            "uri": uri,
        },
        "response": {
            "body": {"string": body},
            "headers": {"Content-Type": ["application/json"]},
            "status": {"code": status_code, "message": "OK"},
        },
    }


def write_cassette(path: Path, interactions: list[dict[str, Any]], *, recorded_at: str | None = None) -> None:
    payload: dict[str, Any] = {"interactions": interactions, "version": 1}
    if recorded_at is not None:
        payload["recorded_at"] = recorded_at
    path.write_text(yaml.safe_dump(payload, default_flow_style=False, allow_unicode=True), encoding="utf-8")


def read_cassette(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def tagged_get(url: str, invocation_tag: str) -> httpx.Response:
    with invocation_context(invocation_tag):
        return httpx.get(url, timeout=2.0)


@pytest.fixture
def make_interaction_fixture() -> Any:
    return make_http_interaction


@pytest.fixture
def write_cassette_fixture() -> Any:
    return write_cassette


@pytest.fixture
def read_cassette_fixture() -> Any:
    return read_cassette


@pytest.fixture
def tagged_get_fixture() -> Any:
    return tagged_get
