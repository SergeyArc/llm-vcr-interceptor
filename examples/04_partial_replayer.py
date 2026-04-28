import asyncio

from examples.utils import get_service
from lhi import LHIInterceptor, ScenarioRow
from lhi.interceptor import DEFAULT_CALLSITE_SKIP_PREFIXES


async def run_partial_replayer() -> None:
    """Mode: Partial Replayer
    Selective replay/live based on callsite-derived tag regex.
    """
    service = get_service()

    async def math_addition() -> str:
        return await service.generate("What is 5 + 7?")

    async def general_q() -> str:
        return await service.generate("What is the capital of France?")

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
        callsite_skip_prefixes=(*DEFAULT_CALLSITE_SKIP_PREFIXES, "examples.utils"),
    )

    async with service:
        with interceptor.use_cassette():
            print("--- Partial Replayer: selective matching by regex ---")

            # math_addition callsite matches regex -> replay if found
            print("Calling math_addition (matches regex)...")
            resp1 = await math_addition()
            print(f"Response 1: {resp1}")

            # general_q callsite does not match -> forces live request in new_episodes mode
            print("\nCalling general_q (doesn't match regex) -> FORCING LIVE REQUEST")
            resp2 = await general_q()
            print(f"Response 2: {resp2}")


if __name__ == "__main__":
    asyncio.run(run_partial_replayer())
