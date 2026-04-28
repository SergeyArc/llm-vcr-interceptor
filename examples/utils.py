from __future__ import annotations

import os
from types import TracebackType

from openai import AsyncOpenAI

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


class OpenAITextGenerator:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    async def __aenter__(self) -> OpenAITextGenerator:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._client.close()


def get_service() -> OpenAITextGenerator:
    if load_dotenv is not None:
        load_dotenv()
    client = AsyncOpenAI(
        api_key=os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("LLM_BASE_URL"),
    )
    model = os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")
    return OpenAITextGenerator(client=client, model=model)
