from __future__ import annotations

import asyncio

from examples.service import get_knowledge_service
from lhi import LHIInterceptor, ScenarioRow, invocation_context


async def main() -> None:
    knowledge_service = get_knowledge_service()
    scenario = ScenarioRow(
        name="freeze_actor_model",
        invocation_patch_regexps=(r"^actor_model_(def|example)$",),
    )
    interceptor = LHIInterceptor(
        sessions={0: "session_0.yaml"},
        scenario=scenario,
    )

    with interceptor.use_cassette():
        async with knowledge_service:
            async def call_with_tag(invocation_tag: str) -> str:
                with invocation_context(invocation_tag):
                    if invocation_tag == "actor_model_def":
                        return await knowledge_service.explain_topic("Actor Model")
                    return await knowledge_service.name_language_using_topic("Actor Model")

            first_response, second_response = await asyncio.gather(
                call_with_tag("actor_model_def"),
                call_with_tag("actor_model_example"),
            )
            print(f"Response 1: {first_response}\n")
            print(f"Response 2: {second_response}\n")


if __name__ == "__main__":
    asyncio.run(main())
