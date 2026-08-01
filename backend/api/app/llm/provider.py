from abc import ABC, abstractmethod
from typing import Any

JsonObject = dict[str, Any]


class LLMProvider(ABC):
    @property
    def is_local(self) -> bool:
        """Whether requests stay inside the operator-controlled boundary."""
        return False

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str: ...

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> JsonObject: ...

    @abstractmethod
    async def health_check(self) -> JsonObject: ...

    async def aclose(self) -> None:
        """Release provider resources when the application shuts down."""
