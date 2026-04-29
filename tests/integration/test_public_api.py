from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

import httpx
import pytest

from lhi import LHIInterceptor, Session, get_current_invocation_tag


def test_interceptor_accepts_session_models(tmp_path: Path, write_cassette_fixture: Any) -> None:
    write_cassette_fixture(tmp_path / "session.yaml", [])
    interceptor = LHIInterceptor(
        sessions=[Session(session_id=0, cassette_path="session.yaml")],
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )
    assert interceptor.cassette_name == "session.yaml"


def test_use_cassette_replay_mode_keeps_recorded_at_unchanged(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    tagged_get_fixture: Any,
    read_cassette_fixture: Any,
) -> None:
    cassette_path = tmp_path / "session.yaml"
    write_cassette_fixture(
        cassette_path,
        [make_interaction_fixture(invocation_tag="tag-1", uri="http://example.com/replay")],
        recorded_at="2026-04-28T07:00:00+00:00",
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="none",
    )

    with interceptor.use_cassette():
        response = tagged_get_fixture("http://example.com/replay", "tag-1")
    assert response.status_code == 200
    assert read_cassette_fixture(cassette_path)["recorded_at"] == "2026-04-28T07:00:00+00:00"


def test_use_cassette_recording_mode_updates_recorded_at(
    tmp_path: Path,
    write_cassette_fixture: Any,
    read_cassette_fixture: Any,
) -> None:
    cassette_path = tmp_path / "session.yaml"
    write_cassette_fixture(cassette_path, [], recorded_at="2026-04-28T07:00:00+00:00")
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="new_episodes",
    )

    with interceptor.use_cassette():
        pass
    first_value = read_cassette_fixture(cassette_path)["recorded_at"]
    with interceptor.use_cassette():
        pass
    second_value = read_cassette_fixture(cassette_path)["recorded_at"]

    assert isinstance(first_value, str)
    assert isinstance(second_value, str)
    assert first_value != "2026-04-28T07:00:00+00:00"
    assert second_value != "2026-04-28T07:00:00+00:00"


@contextmanager
def _serve_json_response(response_body: str) -> Iterator[str]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            encoded = response_body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_record_mode_all_overwrites_previous_interactions(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    read_cassette_fixture: Any,
) -> None:
    cassette_path = tmp_path / "session.yaml"
    write_cassette_fixture(
        cassette_path,
        [make_interaction_fixture(invocation_tag=None, uri="http://legacy.local/old", body='{"source":"old"}')],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="all",
    )

    with _serve_json_response('{"source":"live"}') as base_url:
        with interceptor.use_cassette():
            response = httpx.get(f"{base_url}/fresh", timeout=2.0)
            assert response.status_code == 200

    loaded = read_cassette_fixture(cassette_path)
    interactions = loaded["interactions"]
    assert len(interactions) == 1
    assert interactions[0]["request"]["uri"] == f"{base_url}/fresh"
    assert interactions[0]["response"]["body"]["string"] == '{"source":"live"}'


def test_record_mode_all_first_run_creates_new_cassette(tmp_path: Path, read_cassette_fixture: Any) -> None:
    cassette_path = tmp_path / "session.yaml"
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="all",
    )

    with _serve_json_response('{"source":"first-run"}') as base_url:
        with interceptor.use_cassette():
            response = httpx.get(f"{base_url}/first", timeout=2.0)
            assert response.status_code == 200

    loaded = read_cassette_fixture(cassette_path)
    interactions = loaded["interactions"]
    assert len(interactions) == 1
    assert interactions[0]["request"]["uri"] == f"{base_url}/first"


def test_record_mode_all_repeated_runs_keep_single_interaction(tmp_path: Path, read_cassette_fixture: Any) -> None:
    cassette_path = tmp_path / "session.yaml"
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="all",
    )

    with _serve_json_response('{"source":"run"}') as base_url:
        target_uri = f"{base_url}/same"
        with interceptor.use_cassette():
            first = httpx.get(target_uri, timeout=2.0)
            assert first.status_code == 200
        with interceptor.use_cassette():
            second = httpx.get(target_uri, timeout=2.0)
            assert second.status_code == 200

    loaded = read_cassette_fixture(cassette_path)
    interactions = loaded["interactions"]
    assert len(interactions) == 1
    assert interactions[0]["request"]["uri"] == target_uri


def test_record_mode_new_episodes_keeps_existing_interactions(
    tmp_path: Path,
    write_cassette_fixture: Any,
    make_interaction_fixture: Any,
    read_cassette_fixture: Any,
) -> None:
    cassette_path = tmp_path / "session.yaml"
    legacy_uri = "http://legacy.local/old"
    write_cassette_fixture(
        cassette_path,
        [make_interaction_fixture(invocation_tag=None, uri=legacy_uri, body='{"source":"old"}')],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session.yaml"},
        cassette_library_dir=str(tmp_path),
        record_mode="new_episodes",
    )

    with _serve_json_response('{"source":"new"}') as base_url:
        with interceptor.use_cassette():
            response = httpx.get(f"{base_url}/new", timeout=2.0)
            assert response.status_code == 200

    loaded = read_cassette_fixture(cassette_path)
    uris = [item["request"]["uri"] for item in loaded["interactions"]]
    assert legacy_uri in uris
    assert f"{base_url}/new" in uris
    assert len(uris) == 2


def test_invocation_context_sets_and_resets_tag() -> None:
    from lhi import invocation_context

    assert get_current_invocation_tag() is None
    with invocation_context("tag-1"):
        assert get_current_invocation_tag() == "tag-1"
    assert get_current_invocation_tag() is None


@pytest.mark.asyncio
async def test_invocation_context_concurrent_tags_are_isolated() -> None:
    from lhi import invocation_context

    async def read_tag(tag: str, delay: float) -> str | None:
        with invocation_context(tag):
            await asyncio.sleep(delay)
            return get_current_invocation_tag()

    first_tag, second_tag = await asyncio.gather(
        read_tag("alpha", 0.01),
        read_tag("beta", 0.01),
    )
    assert first_tag == "alpha"
    assert second_tag == "beta"
    assert get_current_invocation_tag() is None
