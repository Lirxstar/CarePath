from typing import Any

from .provider import JsonObject, LLMProvider


class MockLLMProvider(LLMProvider):
    @property
    def is_local(self) -> bool:
        return True

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        return "Mock response"

    async def generate_structured(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> JsonObject:
        del prompt, kwargs
        return {"provider": "mock", "schema": schema}

    async def health_check(self) -> JsonObject:
        return {"status": "ok", "provider": "mock"}
