from __future__ import annotations

from examples.utils import get_llm_api_key, get_llm_base_url, get_llm_model_name, load_llm_environment
from lhi import LHIInterceptor


def run_langchain_basic() -> None:
    """Wrap a LangChain call with a transparent cassette boundary.

    Application code keeps using model.invoke(...), while cassette writes/replays
    are handled automatically inside use_cassette().
    """
    try:
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        msg = "Install optional dependencies first: pip install langchain-openai"
        raise SystemExit(msg) from exc

    load_llm_environment()
    model = ChatOpenAI(
        model=get_llm_model_name(),
        api_key=get_llm_api_key(),
        base_url=get_llm_base_url(),
    )
    interceptor = LHIInterceptor(
        sessions={0: "session_langchain.yaml"},
        record_mode="new_episodes",
    )

    with interceptor.use_cassette():
        response = model.invoke([HumanMessage(content="Explain the Actor Model in one sentence.")])

    print(f"LangChain response (auto replay/record via cassette): {response.content}")


if __name__ == "__main__":
    run_langchain_basic()
