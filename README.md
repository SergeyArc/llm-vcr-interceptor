# vcr_py_test + LHI (прототип)

## LHI (LLM Hub Interceptor)

Модуль [`lhi/`](lhi/) — прототип перехватчика поверх [VCR.py](https://github.com/kevin1024/vcrpy) со следующей структурой:

- [`lhi/session.py`](lhi/session.py): доменные модели сессий и операций правки (`Session`, `AddSession`, `AddRecords`, `RemoveRecords`) для управления составом воспроизводимых записей.
- [`lhi/scenario.py`](lhi/scenario.py): описание сценария `ScenarioRow` (regex по `invocation_tag` + набор `edits`), который определяет правила выбора и модификации кассет.
- [`lhi/context.py`](lhi/context.py): управление контекстом `invocation_tag` (`invocation_context`, `get_current_invocation_tag`) как единый источник тега для matcher и инжекта заголовка.
- [`lhi/interceptor.py`](lhi/interceptor.py): реализация `LHIInterceptor` — инжект `X-Invocation-Tag`, matcher по тегу, виртуальное объединение кассет и синхронизация новых взаимодействий в primary-сессию.
- [`lhi/__init__.py`](lhi/__init__.py): публичный API модуля (`__all__`) для удобного импорта основных сущностей.

Термины:
- **Сессия** — именованный источник записей VCR (обычно один YAML-файл кассеты, например `cassettes/session_0.yaml`), доступный по `session_id`.
- **Сценарий** — правило, которое для текущего `invocation_tag` решает, какие записи оставить из primary-сессии и что добавить/удалить через `edits` (`AddSession`, `AddRecords`, `RemoveRecords`) перед replay.
- **`invocation_tag`** — уникальный тег конкретного LLM-вызова; прокидывается в заголовок `X-Invocation-Tag`, используется в matcher для выбора точной записи из кассеты и в `ScenarioRow.invocation_patch_regexps` для активации сценария.

Формат YAML кассеты:
- верхний уровень содержит `interactions` и `version`;
- поле `recorded_at` опционально и при обновлении кассеты хранит время в формате `datetime.now(UTC).isoformat()`;
- при синхронизации virtual-cassette в primary при совпадении `invocation_tag` запись перезаписывается и логируется `warning`.

Когда проставляется `invocation_tag`:
- рекомендуемый путь: через `with invocation_context("tag"):` вокруг обычного вызова SDK/клиента;
- внутри контекста тег хранится в `ContextVar` на время запроса;
- в `before_record_request` (встроенный хук VCR.py) тег автоматически добавляется в исходящий HTTP-запрос как `X-Invocation-Tag`;
- после выхода из контекста тег сбрасывается.

## Режимы работы

- **Recorder** — принудительно записывает все вызовы в кассету (`record_mode="all"`). Пример: [`examples/01_recorder.py`](examples/01_recorder.py).
- **Replayer** — только воспроизведение из кассеты, без live-запросов (`record_mode="none"`); при отсутствии совпадения запрос падает. Пример: [`examples/02_replayer.py`](examples/02_replayer.py).
- **Hybrid** — воспроизводит существующие записи и дозаписывает новые (`record_mode="new_episodes"`). Пример: [`examples/03_hybrid.py`](examples/03_hybrid.py).
- **Partial Replayer** — выборочный replay по regex в `ScenarioRow.invocation_patch_regexps`; теги вне regex принудительно идут в live (или падают при `record_mode="none"`). Пример: [`examples/04_partial_replayer.py`](examples/04_partial_replayer.py).

Логика `Partial Replayer` (пошагово):
1. Для каждого вызова берётся `invocation_tag` и сравнивается с regex из `ScenarioRow.invocation_patch_regexps`.
2. Если тег **совпал** с regex:
   - вызов допускается к поиску в кассете;
   - матчинг идёт по `X-Invocation-Tag` (тег в запросе должен совпасть с тегом записи).
3. Если тег **не совпал** с regex:
   - matcher принудительно отклоняет кассетную запись для этого вызова;
   - дальше поведение определяет `record_mode`:
     - `new_episodes`/`all`: выполняется live-запрос (и при необходимости записывается),
     - `none`: live запрещён, вызов завершается ошибкой.
4. Если тег совпал с regex, но записи в кассете нет:
   - `new_episodes`/`all`: выполняется live-запрос с последующей записью,
   - `none`: ошибка из-за отсутствия подходящей записи.

## Интеграция без правок SDK

Рекомендуемый паттерн для стандартных SDK и кастомных LLM-клиентов:
1. Обернуть участок работы в `with interceptor.use_cassette():`.
2. Перед конкретным вызовом поставить `invocation_tag` через `with invocation_context("..."):`.
3. Выполнить обычный вызов SDK/клиента.

Минимальный пример:

```python
with interceptor.use_cassette():
    with invocation_context("actor_model_def"):
        response = await service.generate("What is the Actor Model in one sentence?")
```

Ограничения:
- текущий механизм рассчитан на HTTP-перехват через VCR;
- gRPC-based SDK (часть сценариев Gemini/Vertex AI) не покрываются этим путём и требуют отдельного interceptor-слоя.

## Запуск

```bash
# только replay из кассеты (без сети)
VCR_RECORD_MODE=none uv run python main.py

# дозапись новых вызовов (гибрид)
VCR_RECORD_MODE=new_episodes uv run python main.py
```

Кассета по умолчанию: `cassettes/session_0.yaml` (см. `LHIInterceptor` в [`main.py`](main.py)).
