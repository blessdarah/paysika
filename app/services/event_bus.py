from collections import defaultdict
from typing import Any, Callable

_handlers: dict[type, list[Callable]] = defaultdict(list)


def subscribe(event_type: type, handler: Callable) -> None:
    """Subscribe to a domain event type."""
    _handlers[event_type].append(handler)


def publish(event: Any) -> None:
    """Publish a domain event."""
    for handler in _handlers.get(type(event), []):
        handler(event)


def clear_handlers() -> None:
    """Clear all event handlers."""
    _handlers.clear()
