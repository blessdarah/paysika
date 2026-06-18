from decimal import Decimal
from abc import ABC, abstractmethod


class FxProvider(ABC):
    @abstractmethod
    def fetch_rate(self, source: str, target: str) -> Decimal | None:
        ...


_PROVIDERS: dict[str, type[FxProvider]] = {}


def register_provider(name: str):
    def decorator(cls):
        _PROVIDERS[name] = cls
        return cls
    return decorator


def get_provider(name: str) -> FxProvider:
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown FX provider: {name!r}")
    return cls()


from .frankfurter import FrankfurterProvider  # noqa: F401
from .fallback import FallbackProvider  # noqa: F401
