import os
from dotenv import load_dotenv
from llm_actor import LLMActorService, LLMActorSettings

def get_service() -> LLMActorService:
    load_dotenv()
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL_NAME")
    max_concurrency = int(os.getenv("MAX_CONCURRENCY", "2"))
    
    return LLMActorService.from_openai_compatible(
        api_key=api_key,
        model=model,
        base_url=base_url,
        settings=LLMActorSettings(LLM_NUM_ACTORS=max_concurrency),
    )
