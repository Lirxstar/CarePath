from collections.abc import Callable

from .mock import MockLLMProvider
from .provider import LLMProvider
from .radeon_local import RadeonLocalProvider

ProviderFactory = Callable[[], LLMProvider]
_PROVIDERS: dict[str, ProviderFactory] = {
    "mock": MockLLMProvider,
    "radeon_local": RadeonLocalProvider,
}


def register_provider(name: str, factory: ProviderFactory, *, replace: bool = False) -> None:
    normalized_name = name.strip().lower()
    if not normalized_name:
        raise ValueError("Provider name must not be empty")
    if normalized_name in _PROVIDERS and not replace:
        raise ValueError(f"Provider already registered: {normalized_name}")
    _PROVIDERS[normalized_name] = factory


def get_provider(name: str) -> LLMProvider:
    normalized_name = name.strip().lower()
    try:
        factory = _PROVIDERS[normalized_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported provider: {normalized_name}") from exc
    provider = factory()
    if not isinstance(provider, LLMProvider):
        raise TypeError(f"Provider factory did not return LLMProvider: {normalized_name}")
    return provider


def available_providers() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))
