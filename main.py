from __future__ import annotations

import asyncio
import os

import vcr
from dotenv import load_dotenv
from llm_actor import LLMActorService, LLMActorSettings


def _build_vcr() -> vcr.VCR:
    return vcr.VCR(
        cassette_library_dir=os.environ.get("VCR_CASSETTES_DIR", "cassettes"),
        record_mode=os.environ.get("VCR_RECORD_MODE", "none"),
        filter_headers=(
            "authorization",
            "api-key",
            "x-api-key",
        ),
        match_on=("method", "scheme", "host", "port", "path", "query"),
    )


async def main() -> None:
    load_dotenv()
    api_key = os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL_NAME")
    max_concurrency = os.environ.get("MAX_CONCURRENCY")

    service = LLMActorService.from_openai_compatible(
        api_key=api_key,
        model=model,
        base_url=base_url,
        settings=LLMActorSettings(LLM_NUM_ACTORS=max_concurrency),
    )

    vcr_instance = _build_vcr()
    cassette_name = os.environ.get("VCR_CASSETTE", "llm_generate.yaml")

    with vcr_instance.use_cassette(cassette_name):
        async with service:
            first_response = await service.generate("What is the Actor Model in one sentence?")
            print(f"Response: {first_response}\n")

            second_response = await service.generate(
                f'Given this summary: "{first_response}"\n'
                "Give one concrete software system that applies the actor model, in one short phrase."
            )
            print(f"Follow-up: {second_response}\n")


if __name__ == "__main__":
    asyncio.run(main())
