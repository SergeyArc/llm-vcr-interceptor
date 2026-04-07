# LHI Examples

This directory contains examples for different operation modes of the LLM Hub Interceptor.

## Common requirements
Make sure you have your `.env` file configured with `LLM_API_KEY` and `LLM_BASE_URL`.

## Running examples

Use `uv run` to execute the scripts from the project root:

1. **Recorder** (Always record everything):
   ```bash
   uv run python examples/01_recorder.py
   ```

2. **Replayer** (Deterministic playback, no network):
   ```bash
   uv run python examples/02_replayer.py
   ```

3. **Hybrid** (Existing record + record new):
   ```bash
   uv run python examples/03_hybrid.py
   ```

4. **Partial Replayer** (Selective replay by regex):
   ```bash
   uv run python examples/04_partial_replayer.py
   ```

## Modes overview

- **Recorder**: All calls are recorded in a session file.
- **Replayer**: All calls are read from a session file. No new interactions are allowed.
- **Recorder + Replayer**: New calls are recorded, old ones are replayed. Helps incrementally build the test suite.
- **Partial Replayer**: Use regex selectors on `invocation_tag` to define what should be replayed and what should go live.
