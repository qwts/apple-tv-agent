"""Validated requests keep typed text out of their representation."""

from dataclasses import dataclass, field

from apple_tv_agent.models import Command


@dataclass(frozen=True)
class Request:
    command: Command
    device: str | None = None
    timeout: float = 15
    host: str | None = None
    name: str | None = None
    app_id: str | None = None
    level: float | None = None
    network: bool = False
    text: str | None = field(default=None, repr=False)
