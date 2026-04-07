from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from llm_actor import LLMActorService, LLMActorSettings


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

    async with service:
        response = await service.generate("What is the Actor Model in one sentence?")
        print(f"Response: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
