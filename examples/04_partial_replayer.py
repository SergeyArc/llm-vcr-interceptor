import asyncio

from examples.service import get_knowledge_service
from lhi import LHIInterceptor, ScenarioRow
from lhi.interceptor import DEFAULT_CALLSITE_SKIP_PREFIXES


async def run_partial_replayer() -> None:
    """Mode: Partial Replayer
    No explicit cassette write/read calls in business code.
    Selective replay/live based on callsite-derived tag regex.
    """
    knowledge_service = get_knowledge_service()

    async def math_addition() -> str:
        return await knowledge_service.answer_math_question("What is 5 + 7?")

    async def general_q() -> str:
        return await knowledge_service.answer_question("What is the capital of France?")

    # Replay only requests emitted from math_addition callsite.
    scenario = ScenarioRow(
        name="selective_replay",
        invocation_patch_regexps=(r"^callsite:examples/04_partial_replayer\.py:math_addition:.*",),
    )

    interceptor = LHIInterceptor(
        sessions={0: "session_0.yaml"},
        scenario=scenario,
        record_mode="new_episodes",
        identity_strategy="callsite",
        callsite_skip_prefixes=(*DEFAULT_CALLSITE_SKIP_PREFIXES, "examples.service"),
    )

    async with knowledge_service:
        with interceptor.use_cassette():
            print("--- Partial Replayer: automatic cassette I/O + selective regex matching ---")

            # math_addition callsite matches regex -> replay if found
            print("Calling math_addition (matches regex)...")
            resp1 = await math_addition()
            print(f"Response 1: {resp1}")

            # general_q callsite does not match -> forced live passthrough (not recorded in this cassette)
            print("\nCalling general_q (doesn't match regex) -> FORCING LIVE REQUEST")
            resp2 = await general_q()
            print(f"Response 2: {resp2}")


if __name__ == "__main__":
    asyncio.run(run_partial_replayer())
