import asyncio

from examples.utils import get_service
from lhi import LHIInterceptor


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
            resp1 = await interceptor.generate(service, "What is the Actor Model in one sentence?", "actor_model_def")
            print(f"Response 1: {resp1[:50]}...")

            # This will be RECORDED to session_0.yaml if it's new
            resp2 = await interceptor.generate(service, "Translate 'Hello' to French.", "translation_hello")
            print(f"Response 2 (newly recorded or replayed): {resp2}")


if __name__ == "__main__":
    asyncio.run(run_hybrid())
