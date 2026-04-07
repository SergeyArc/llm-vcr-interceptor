from __future__ import annotations

import asyncio

from examples.utils import get_service
from lhi import LHIInterceptor, ScenarioRow


async def main() -> None:
    service = get_service()
    scenario = ScenarioRow(
        name="freeze_actor_model",
        invocation_patch_regexps=[r"^actor_model_(def|example)$"],
    )
    interceptor = LHIInterceptor(
        sessions={0: "session_0.yaml"},
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
