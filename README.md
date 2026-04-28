# llm-vcr-interceptor

Cache LLM API responses and replay them instantly — save money and time when iterating on ML pipelines.

---

## Why use this?

Every time you develop or debug a pipeline that calls an LLM, you pay for the same requests over and over. This package records model responses once, then replays them instantly — no API calls needed.

**Typical scenario:** you have a 10-step pipeline. You're iterating on step 8. Steps 1–7 are already working — no need to run them every time.

---

## Alternatives and why this library can be a better fit

### [LLM Intercept](https://github.com/mlech26l/llm_intercept)

`llm_intercept` is an OpenAI-compatible proxy focused on dataset collection for fine-tuning. It stores requests in SQLite, supports streaming and tool calls, and exports successful records to `JSONL.zstd` or Parquet.

Why this project can be better for pipeline iteration:
- It is focused on deterministic replay inside application code, not on proxy-level traffic collection.
- It supports named call-level control via `invocation_context("...")` to freeze specific pipeline steps.
- It provides scenario-driven session composition (`ScenarioRow`, `AddSession`, `AddRecords`, `RemoveRecords`) for selective replay and refresh.

### [cached stubs pattern (article)](https://louisabraham.github.io/articles/cached-stubs)

`cached stubs` is an engineering pattern described in an article (with an implementation in `malib`), where function outputs are cached with `joblib` and patched in tests.

Why this project can be better for HTTP LLM workflows:
- It targets HTTP LLM traffic directly, so you can replay external API responses without patching each function manually.
- It gives one consistent cassette workflow for dev and CI, including strict replay (`record_mode="none"`).
- It keeps cache control at LLM invocation boundaries, which is easier to reason about in multi-step LLM pipelines.

### [llm_recorder](https://github.com/zby/llm_recorder)

`llm_recorder` records and replays LLM interactions and is useful for chained calls. It replays a configured number of calls (`replay_count`) and then falls back to live calls. The README also documents a synchronous-only limitation.

Why this project can be better for strict reproducibility:
- It supports strict no-network replay mode (`record_mode="none"`) for deterministic CI runs.
- It offers partial replay by regex to freeze early steps and keep later steps live in the same run.
- It includes session merge/cherry-pick primitives, so you can compose reusable datasets across runs.

### [VCR.py](https://github.com/kevin1024/vcrpy)

`VCR.py` is the core, mature solution for HTTP cassette recording/replay with rich customization (`match_on`, request/response filtering hooks, serializers/persisters).
This library is built on top of VCR.py and extends it for LLM pipeline workflows.

Why this project can be better for LLM-specific development:
- It adds LLM-native invocation tagging (`invocation_context`) on top of VCR mechanics.
- It adds pipeline-aware scenario editing (`ScenarioRow` + session edits), which VCR.py does not provide out of the box.
- It keeps VCR.py compatibility while exposing a higher-level API tailored for iterative LLM pipelines.

### Why choose this library

- You need deterministic replays for LLM pipelines with explicit step names, not only raw HTTP matching.
- You iterate on later pipeline stages and want selective freezing of earlier stages.
- You need to merge, cherry-pick, or refresh cached records across multiple sessions.
- You want one flow for local development (`new_episodes`) and strict CI replay (`none`).
- You want async-compatible usage without changing your OpenAI-style call sites.

---

## Installation

```bash
pip install llm-vcr-interceptor
```

---

## Quickstart (5 minutes)

Say you have existing OpenAI code:

```python
from openai import OpenAI

client = OpenAI(api_key="...")

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "What is the Actor Model?"}],
)
print(response.choices[0].message.content)
```

Wrap it with three lines:

```python
from openai import OpenAI
from lhi import LHIInterceptor, invocation_context  # 1. import

client = OpenAI(api_key="...")
interceptor = LHIInterceptor(sessions={0: "my_session.yaml"})  # 2. create

with interceptor.use_cassette():  # 3. wrap
    with invocation_context("actor_model_def"):  # unique name for this call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "What is the Actor Model?"}],
        )
        print(response.choices[0].message.content)
```

- **First run** — a real API call is made and the response is saved to `cassettes/my_session.yaml`.
- **Every subsequent run** — the response is loaded from the file, no API call is made.

> **`invocation_context`** is a unique name for a specific call. The package uses it to find the right cached response. Name it clearly: `"summarize_article"`, `"extract_entities_step2"`, etc.

---

## Choose a mode

| Mode | When to use | `record_mode` |
|------|-------------|---------------|
| **Recorder** | First run — record all responses | `"all"` |
| **Replayer** | Testing, CI/CD — no live requests allowed | `"none"` |
| **Hybrid** (default) | Development — cached responses reused, new ones recorded | `"new_episodes"` |
| **Partial Replayer** | Freeze some steps, let others hit the real API | `ScenarioRow` |

### Recorder (`record_mode="all"`)

Always calls the real API and overwrites the cache. Use for the initial run or to refresh all responses.

```python
interceptor = LHIInterceptor(
    sessions={0: "my_session.yaml"},
    record_mode="all",
)
```

### Replayer (`record_mode="none"`)

Cache only — raises an error if a cached response is missing. Use for CI/CD and deterministic tests.

```python
interceptor = LHIInterceptor(
    sessions={0: "my_session.yaml"},
    record_mode="none",
)
```

### Hybrid (`record_mode="new_episodes"`, default)

If a response is cached — use it. If not — call the API and save the response. The most convenient mode during development.

```python
interceptor = LHIInterceptor(
    sessions={0: "my_session.yaml"},
    # record_mode="new_episodes" is the default
)
```

### Partial Replayer

Freeze early pipeline steps while iterating on later ones. Use `ScenarioRow` with a regex pattern on the call name.

```python
from lhi import LHIInterceptor, ScenarioRow, invocation_context

# Steps named "preprocess_*" are served from cache.
# Everything else hits the real API.
scenario = ScenarioRow(
    name="freeze_preprocessing",
    invocation_patch_regexps=(r"^preprocess_.*",),
)

interceptor = LHIInterceptor(
    sessions={0: "my_session.yaml"},
    scenario=scenario,
    record_mode="new_episodes",
)

with interceptor.use_cassette():
    with invocation_context("preprocess_step1"):
        pass  # served from cache

    with invocation_context("generate_report"):
        pass  # real API call
```

---

## Working with multiple sessions

You can store responses in multiple files and combine them. Useful when different parts of a pipeline were recorded at different times or by different people.

### Merge two sessions

```python
from lhi import LHIInterceptor, ScenarioRow
from lhi.session import AddSession

scenario = ScenarioRow(
    name="merged",
    invocation_patch_regexps=(),
    edits=(
        AddSession(session_id=0),  # base session
        AddSession(session_id=1),  # overrides records with the same name
    ),
)

interceptor = LHIInterceptor(
    sessions={
        0: "session_base.yaml",
        1: "session_updated.yaml",
    },
    scenario=scenario,
    record_mode="none",
)
```

### Cherry-pick specific records from another session

```python
from lhi import LHIInterceptor, ScenarioRow
from lhi.session import AddSession, AddRecords

scenario = ScenarioRow(
    name="cherry_pick",
    invocation_patch_regexps=(),
    edits=(
        AddSession(session_id=0),
        AddRecords(session_id=1, tags=("special_step",)),  # only this one
    ),
)
```

### Force-refresh specific cached responses

Remove records from the cache — on the next run they will hit the real API and be overwritten.

```python
from lhi import LHIInterceptor, ScenarioRow
from lhi.session import AddSession, RemoveRecords

scenario = ScenarioRow(
    name="refresh_late_stages",
    invocation_patch_regexps=(),
    edits=(
        AddSession(session_id=0),
        RemoveRecords(tags=("late_stage_.*",)),  # these will be re-recorded
    ),
)
```

---

## Async code

Works with `async/await` out of the box:

```python
import asyncio
from openai import AsyncOpenAI
from lhi import LHIInterceptor, invocation_context

client = AsyncOpenAI(api_key="...")
interceptor = LHIInterceptor(sessions={0: "my_session.yaml"})

async def main():
    with interceptor.use_cassette():
        with invocation_context("my_step"):
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hello!"}],
            )
            print(response.choices[0].message.content)

asyncio.run(main())
```

---

## LangChain and LlamaIndex

LangChain and LlamaIndex work without native adapters when their providers use regular HTTP clients under the hood. Keep `LHIInterceptor` at the cassette boundary and put `invocation_context()` around the framework call you want to cache.

Install the LangChain OpenAI provider before running the example:

```bash
pip install langchain-openai
```

```python
from langchain_openai import ChatOpenAI
from lhi import LHIInterceptor, invocation_context

model = ChatOpenAI(model="gpt-4o-mini")
interceptor = LHIInterceptor(sessions={0: "langchain.yaml"})

with interceptor.use_cassette():
    with invocation_context("summarize_article"):
        response = model.invoke("Summarize this article in one paragraph.")

print(response.content)
```

For LlamaIndex use the same pattern around the query or workflow step:

```python
with interceptor.use_cassette():
    with invocation_context("retrieve_answer"):
        response = query_engine.query("What changed in the latest report?")
```

If one `chain.invoke()` performs several hidden LLM or embedding calls, split the workflow into explicit steps and give each step its own `invocation_context()`. This keeps cassette records stable and avoids framework-specific callback dependencies in the core package.

---

## Examples

Run the ready-made examples from the project root:

```bash
# Full example with concurrent calls
uv run python examples/quickstart.py

# Recorder mode
uv run python examples/01_recorder.py

# Replayer mode
uv run python examples/02_replayer.py

# Hybrid mode
uv run python examples/03_hybrid.py

# Partial replay by regex
uv run python examples/04_partial_replayer.py

# LangChain integration through invocation_context
uv run python examples/05_langchain_basic.py
```

---

## Streaming (SSE)

- `text/event-stream` responses are normalized to a full body before cassette write.
- On replay, the stream is served with cursor-safe chunk iteration to avoid restarting from the beginning.
- SSE chunks are emitted by event boundary (`\n\n`) for deterministic event parsing.

---

## API Reference

| Object | Description |
|--------|-------------|
| `LHIInterceptor(sessions, scenario, cassette_library_dir, record_mode)` | Main object. `sessions` is a dict `{id: "file.yaml"}` |
| `interceptor.use_cassette()` | Context manager that activates the cache |
| `invocation_context("name")` | Context manager that sets the name of the current call |
| `get_current_invocation_tag()` | Returns the current call name |
| `ScenarioRow(name, invocation_patch_regexps, edits)` | Rules for selective replay |
| `AddSession(session_id)` | Include all records from a session |
| `AddRecords(session_id, tags)` | Include specific records from a session |
| `RemoveRecords(tags)` | Remove records from cache (force a live API call) |

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VCR_CASSETTES_DIR` | `cassettes` | Directory for cache files |
| `VCR_RECORD_MODE` | `new_episodes` | Recording mode |
| `LHI_STREAM_MAX_BODY_BYTES` | `10485760` | Max SSE body size to normalize into cassette |

---

## Limitations

- Works with HTTP traffic only (OpenAI, Anthropic, Mistral, and other REST APIs).
- gRPC clients are not supported.
- SSE replay preserves event content/order but not original timing between events.
- SSE normalization is limited to 10 MiB by default (override via `LHI_STREAM_MAX_BODY_BYTES`).

---

## Local Development

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

### Package structure

- `lhi/interceptor.py` — `LHIInterceptor`: tag injection, matching, virtual cassette merge.
- `lhi/scenario.py` — `ScenarioRow`: selective replay rules.
- `lhi/session.py` — `Session`, `AddSession`, `AddRecords`, `RemoveRecords`.
- `lhi/context.py` — `invocation_context`, `get_current_invocation_tag`.
