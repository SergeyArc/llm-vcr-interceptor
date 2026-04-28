import asyncio

from examples.utils import get_service
from lhi import LHIInterceptor, invocation_context


async def run_hybrid() -> None:
    """Mode: Recorder + Replayer (record_mode='new_episodes')
    Hybrid mode: use existing records, record anything new.
    """
    service = get_service()
    interceptor = LHIInterceptor(
        sessions={0: "session_0.yaml"},
        record_mode="new_episodes",  # Default mode
    )

    async with service:
        with interceptor.use_cassette():
            print("--- Hybrid Mode: Replay existing + Record new ---")
            # This should be replayed if in session_0.yaml
            with invocation_context("actor_model_def"):
                resp1 = await service.generate("What is the Actor Model in one sentence?")
            print(f"Response 1: {resp1[:50]}...")

            # This will be RECORDED to session_0.yaml if it's new
            with invocation_context("translation_hello"):
                resp2 = await service.generate("Translate 'Hello' to French.")
            print(f"Response 2 (newly recorded or replayed): {resp2}")


if __name__ == "__main__":
    asyncio.run(run_hybrid())
