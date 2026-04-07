from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from llm_actor import LLMActorService, LLMActorSettings

from lhi import AddRecords, AddSession, LHIInterceptor, RemoveRecords, ScenarioRow


async def main() -> None:
    load_dotenv()
    api_key = os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL_NAME")
    max_concurrency = os.environ.get("MAX_CONCURRENCY")

    service = LLMActorService.from_openai_compatible(
        api_key=api_key,
        model=model,
        base_url=base_url,
        settings=LLMActorSettings(LLM_NUM_ACTORS=max_concurrency),
    )

    from lhi.trial.registry import get_scenario, SESSIONS
    scenario = get_scenario("freeze_actor_model")
    interceptor = LHIInterceptor(
        sessions=SESSIONS,
        scenario=scenario,
    )

    with interceptor.use_cassette():
        async with service:
            first_response, second_response = await asyncio.gather(
                interceptor.generate(
                    service,
                    "What is the Actor Model in one sentence?",
                    "actor_model_def",
                ),
                interceptor.generate(
                    service,
                    "Name one language that uses the Actor Model.",
                    "actor_model_example",
                ),
            )
            print(f"Response 1: {first_response}\n")
            print(f"Response 2: {second_response}\n")


if __name__ == "__main__":
    asyncio.run(main())
