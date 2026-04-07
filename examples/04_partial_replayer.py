import asyncio

from examples.utils import get_service
from lhi import LHIInterceptor, ScenarioRow


async def run_partial_replayer() -> None:
    """Mode: Partial Replayer
    Selective replay/live based on tag regex (invocation_patch_regexps).
    """
    service = get_service()

    # This scenario only allows replaying calls where the tag matches the regex.
    # Otherwise it forces a live call (or fails in 'none' mode).
    scenario = ScenarioRow(
        name="selective_replay",
        invocation_patch_regexps=[r"^math_.*"],  # Only match mathematical tags for replay
    )

    interceptor = LHIInterceptor(
        sessions={0: "session_0.yaml"},
        scenario=scenario,
        record_mode="new_episodes",
    )

    async with service:
        with interceptor.use_cassette():
            print("--- Partial Replayer: selective matching by regex ---")

            # This tag "math_addition" MATCHES the regex -> will be replayed if found
            print("Calling math_addition (matches regex)...")
            resp1 = await interceptor.generate(service, "What is 5 + 7?", "math_addition")
            print(f"Response 1: {resp1}")

            # This tag "general_q" DOES NOT match the regex -> forces live call
            print("\nCalling general_q (doesn't match regex) -> FORCING LIVE REQUEST")
            resp2 = await interceptor.generate(service, "What is the capital of France?", "general_q")
            print(f"Response 2: {resp2}")


if __name__ == "__main__":
    asyncio.run(run_partial_replayer())
