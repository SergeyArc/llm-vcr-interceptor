# llm-vcr-interceptor

`llm-vcr-interceptor` is an invocation-tag-aware replay layer for LLM HTTP traffic built on top of [VCR.py](https://github.com/kevin1024/vcrpy).

It helps you:
- replay deterministic LLM requests by `X-Invocation-Tag`;
- merge and patch recorded interactions across multiple sessions;
- run pure replay, hybrid record/replay, or full recorder modes.

## Installation

```bash
pip install llm-vcr-interceptor
```

## Quickstart

```python
from lhi import LHIInterceptor, invocation_context

interceptor = LHIInterceptor(
    sessions={0: "session_0.yaml"},
    cassette_library_dir="cassettes",
    record_mode="new_episodes",
)

with interceptor.use_cassette():
    with invocation_context("actor_model_def"):
        # Call your regular HTTP-based LLM SDK here.
        pass
```

Run the end-to-end example:

```bash
uv run python examples/quickstart.py
```

## Public API

- `LHIInterceptor`: main VCR wrapper with invocation-tag matcher.
- `invocation_context`: context manager for setting request-scoped invocation tags.
- `get_current_invocation_tag`: helper to read the current invocation tag.
- `ScenarioRow`, `AddSession`, `AddRecords`, `RemoveRecords`: selective replay and patching primitives.

## Record Modes

- `record_mode="none"`: replay only, no live requests.
- `record_mode="new_episodes"`: replay existing and append missing interactions.
- `record_mode="all"`: always record fresh interactions.

## Limitations

- The interceptor works for HTTP traffic intercepted by VCR.py.
- gRPC-based SDK flows require a separate interception strategy.

## Local Development

```bash
uv run ruff check .
uv run mypy
uv run pytest
```


### Module Overview

- `lhi/session.py`: domain models for session sources and scenario edit operations (`Session`, `AddSession`, `AddRecords`, `RemoveRecords`).
- `lhi/scenario.py`: `ScenarioRow` definition (`invocation_tag` regex + `edits`) that controls selective replay behavior.
- `lhi/context.py`: invocation tag context management via `invocation_context` and `get_current_invocation_tag`.
- `lhi/interceptor.py`: `LHIInterceptor` implementation (inject `X-Invocation-Tag`, match by tag, merge virtual cassette, sync updates to primary session).
- `lhi/__init__.py`: package public API exports.

### Key Terms

- **Session**: named source of VCR interactions (usually one cassette file, for example `cassettes/session_0.yaml`) referenced by `session_id`.
- **Scenario**: rule set applied for a current `invocation_tag` that can keep, add, or remove replay interactions via `AddSession`, `AddRecords`, and `RemoveRecords`.
- **invocation_tag**: unique tag of a single LLM call, injected into `X-Invocation-Tag`, used by matcher logic to select exact cassette interactions, and used by `ScenarioRow.invocation_patch_regexps` to activate scenario rules.

## Release Checklist

1. Ensure package name availability on PyPI:
   - `pip index versions llm-vcr-interceptor`
2. Bump version in `lhi/__init__.py` (`__version__`).
3. Build artifacts:
   - `uv build`
4. Validate artifacts:
   - `uv run twine check dist/*`
5. Publish:
   - `uv run twine upload dist/*`
