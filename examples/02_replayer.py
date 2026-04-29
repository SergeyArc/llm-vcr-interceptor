import asyncio

from examples.service import get_knowledge_service
from lhi import LHIInterceptor


async def run_replayer() -> None:
    """Mode: Replayer (record_mode='none')
    Transparent mode: no explicit replay/read calls in business code.
    Deterministic playback from an existing session.
    Fails if a match is not found.
    """
    knowledge_service = get_knowledge_service()
    interceptor = LHIInterceptor(
        sessions={0: "session_0.yaml"},
        record_mode="none",  # Strict replay: no live requests allowed
    )

    async with knowledge_service:
        with interceptor.use_cassette():
            print("--- Replayer: automatic cassette replay from session_0.yaml ---")
            try:
                resp = await knowledge_service.explain_topic("Actor Model")
                print(f"Response (cached): {resp}")
            except Exception as e:
                print(f"Error (expected if cassette body mismatch or live restricted): {e}")


if __name__ == "__main__":
    asyncio.run(run_replayer())
