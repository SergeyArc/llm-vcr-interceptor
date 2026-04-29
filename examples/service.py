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


class KnowledgeService:
    def __init__(self, text_generator: OpenAITextGenerator) -> None:
        self._text_generator = text_generator

    async def answer_math_question(self, question: str) -> str:
        return await self._text_generator.generate(question)

    async def explain_topic(self, topic: str) -> str:
        prompt = f"What is {topic} in one sentence?"
        return await self._text_generator.generate(prompt)

    async def translate_text(self, text: str, target_language: str) -> str:
        prompt = f"Translate '{text}' to {target_language}."
        return await self._text_generator.generate(prompt)

    async def answer_question(self, question: str) -> str:
        return await self._text_generator.generate(question)

    async def name_language_using_topic(self, topic: str) -> str:
        prompt = f"Name one language that uses the {topic}."
        return await self._text_generator.generate(prompt)

    async def __aenter__(self) -> KnowledgeService:
        await self._text_generator.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._text_generator.__aexit__(exc_type, exc_val, exc_tb)


def _build_text_generator() -> OpenAITextGenerator:
    if load_dotenv is not None:
        load_dotenv()
    client = AsyncOpenAI(
        api_key=os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("LLM_BASE_URL"),
    )
    model = os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")
    return OpenAITextGenerator(client=client, model=model)


def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService(text_generator=_build_text_generator())


def load_llm_environment() -> None:
    if load_dotenv is not None:
        load_dotenv()


def get_llm_api_key() -> str | None:
    return os.environ.get("LLM_API_KEY")


def get_llm_base_url() -> str | None:
    return os.environ.get("LLM_BASE_URL")


def get_llm_model_name() -> str:
    return os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")
