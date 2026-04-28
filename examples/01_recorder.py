import asyncio

from examples.utils import get_service
from lhi import LHIInterceptor


async def run_recorder() -> None:
    """Mode: Recorder (record_mode='all')
    Transparent mode: business code calls stay unchanged.
    Cassette records are written automatically inside use_cassette().
    """
    service = get_service()
    interceptor = LHIInterceptor(
        sessions={0: "session_recorder.yaml"},
        record_mode="all",  # Force recording of all requests
    )

    async with service:
        with interceptor.use_cassette():
            print("--- Recorder: automatic cassette write to session_recorder.yaml ---")
            resp = await service.generate("What is 2+2?")
            print(f"Response: {resp}")


if __name__ == "__main__":
    asyncio.run(run_recorder())
