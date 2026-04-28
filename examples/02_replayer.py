import asyncio

from examples.utils import get_service
from lhi import LHIInterceptor


async def run_replayer() -> None:
    """Mode: Replayer (record_mode='none')
    Deterministic playback from an existing session.
    Fails if a match is not found.
    """
    service = get_service()
    interceptor = LHIInterceptor(
        sessions={0: "session_0.yaml"},
        record_mode="none",  # Strict replay: no live requests allowed
    )

    async with service:
        with interceptor.use_cassette():
            print("--- Replaying calls from session_0.yaml ---")
            try:
                resp = await service.generate("What is the Actor Model in one sentence?")
                print(f"Response (cached): {resp}")
            except Exception as e:
                print(f"Error (expected if cassette body mismatch or live restricted): {e}")


if __name__ == "__main__":
    asyncio.run(run_replayer())
