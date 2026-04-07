# vcr_py_test + LHI (прототип)

## LHI (LLM Hub Interceptor)

Модуль [`lhi/`](lhi/) — прототип: `ScenarioRow` (regex по `invocation_tag`), `Session` / `AddSession`, `LHIInterceptor` поверх [VCR.py](https://github.com/kevin1024/vcrpy).

**Важно:** `llm_actor` выполняет HTTP в воркерах пула, поэтому тег передаётся через `_pending_invocation_tag` под `asyncio.Lock` на время `await service.generate()`, а не через `ContextVar`.

## Запуск

```bash
# только replay из кассеты (без сети)
VCR_RECORD_MODE=none uv run python main.py

# дозапись новых вызовов (гибрид)
VCR_RECORD_MODE=new_episodes uv run python main.py
```

Кассета по умолчанию: `cassettes/session_0.yaml` (см. `LHIInterceptor` в [`main.py`](main.py)).
