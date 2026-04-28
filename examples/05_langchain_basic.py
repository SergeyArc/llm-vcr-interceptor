from __future__ import annotations

import os

from dotenv import load_dotenv

from lhi import LHIInterceptor, invocation_context


def run_langchain_basic() -> None:
    """Wrap a LangChain call with the existing LHI cassette boundary."""
    try:
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        msg = "Install optional dependencies first: pip install langchain-openai"
        raise SystemExit(msg) from exc

    load_dotenv()
    model = ChatOpenAI(
        model=os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini"),
        api_key=os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("LLM_BASE_URL"),
    )
    interceptor = LHIInterceptor(
        sessions={0: "session_langchain.yaml"},
        record_mode="new_episodes",
    )

    with interceptor.use_cassette():
        with invocation_context("langchain_actor_model"):
            response = model.invoke([HumanMessage(content="Explain the Actor Model in one sentence.")])

    print(response.content)


if __name__ == "__main__":
    run_langchain_basic()
