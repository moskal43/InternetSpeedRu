"""Runtime state for InternetSpeedRu."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

_ResultT = TypeVar("_ResultT")


class RunBlocking(Protocol):
    """Run blocking adapter work outside the Home Assistant event loop."""

    def __call__(
        self,
        target: Callable[..., _ResultT],
        *args: Any,
    ) -> Awaitable[_ResultT]:
        """Schedule blocking work and return its eventual result."""


@dataclass(slots=True)
class InternetSpeedRuRuntime:
    """Dependencies owned by one InternetSpeedRu config entry."""

    run_blocking: RunBlocking
