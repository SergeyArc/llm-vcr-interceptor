# LHI Examples

This directory contains examples for different operation modes of `llm-vcr-interceptor`.

## Common requirements
Make sure you have your `.env` file configured with `LLM_API_KEY` and `LLM_BASE_URL`.

## Transparent cassette behavior
- Your application code stays unchanged: keep calling `service.generate(...)` or `model.invoke(...)`.
- You do not call any explicit "record/save cassette" API in business code.
- `LHIInterceptor.use_cassette()` creates one cassette boundary and automatically records/replays HTTP calls inside it.

## Running examples

Use `uv run` to execute the scripts from the project root:

1. **Quickstart** (Advanced flow with `ScenarioRow` + tagged concurrent calls):
   ```bash
   uv run python examples/quickstart.py
   ```

2. **Recorder** (Always record everything):
   ```bash
   uv run python examples/01_recorder.py
   ```

3. **Replayer** (Deterministic playback, no network):
   ```bash
   uv run python examples/02_replayer.py
   ```

4. **Hybrid** (Existing record + record new):
   ```bash
   uv run python examples/03_hybrid.py
   ```

5. **Partial Replayer** (Selective replay by callsite regex, no explicit tags):
   ```bash
   uv run python examples/04_partial_replayer.py
   ```

6. **LangChain Basic** (Transparent replay at cassette boundary):
   ```bash
   uv run python examples/05_langchain_basic.py
   ```

## Modes overview

- **Recorder**: All calls are recorded in a session file.
- **Replayer**: All calls are read from a session file. No new interactions are allowed.
- **Recorder + Replayer**: New calls are recorded, old ones are replayed. Helps incrementally build the test suite.
- **Partial Replayer**: Use regex selectors on `invocation_tag` to define what should be replayed and what should go live.
- **LangChain Basic**: Keep replay transparent; only cassette boundary is required.

## Transparent vs advanced examples

- `01_recorder.py`, `02_replayer.py`, `03_hybrid.py`, `05_langchain_basic.py` use transparent replay (no `invocation_context` and no explicit record/save calls in business code).
- `04_partial_replayer.py` shows callsite-based selective replay without explicit tags.
- `quickstart.py` shows explicit named-step control with `invocation_context` and `ScenarioRow`.
