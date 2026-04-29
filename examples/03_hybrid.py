import asyncio

from examples.service import get_knowledge_service
from lhi import LHIInterceptor


async def run_hybrid() -> None:
    """Mode: Recorder + Replayer (record_mode='new_episodes')
    Transparent mode: business code stays unchanged.
    Hybrid mode: use existing records, record anything new.
    """
    knowledge_service = get_knowledge_service()
    interceptor = LHIInterceptor(
        sessions={0: "session_0.yaml"},
        record_mode="new_episodes",  # Default mode
    )

    async with knowledge_service:
        with interceptor.use_cassette():
            print("--- Hybrid: automatic replay existing + auto-record new ---")
            # This should be replayed if in session_0.yaml
            resp1 = await knowledge_service.explain_topic("Actor Model")
            print(f"Response 1: {resp1[:50]}...")

            # This will be RECORDED to session_0.yaml if it's new
            resp2 = await knowledge_service.translate_text("Hello", "French")
            print(f"Response 2 (newly recorded or replayed): {resp2}")


if __name__ == "__main__":
    asyncio.run(run_hybrid())
