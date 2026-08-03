from typing import Any

from .provider import JsonObject, LLMProvider


class RadeonLocalProvider(LLMProvider):
    """AMD Radeon/ROCm provider boundary.

    The first implementation intentionally keeps model execution behind this
    contract. Runtime-specific loading is enabled only when an AMD environment
    and local model configuration are available.
    """

    def __init__(self) -> None:
        self._model_id = "unconfigured"
        self._runtime = "rocm"

    @property
    def is_local(self) -> bool:
        return True

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        raise RuntimeError(
            "Radeon local inference runtime is not configured. "
            "Set AMD model/runtime configuration before execution."
        )

    async def generate_structured(
        self,
        prompt: str,
        schema: JsonObject,
        **kwargs: Any,
    ) -> JsonObject:
        del prompt, schema, kwargs
        raise RuntimeError(
            "Radeon local inference runtime is not configured. "
            "Set AMD model/runtime configuration before execution."
        )

    async def health_check(self) -> JsonObject:
        return {
            "status": "not_ready",
            "provider": "radeon_local",
            "runtime": self._runtime,
            "model": self._model_id,
            "local": True,
        }
