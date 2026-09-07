"""Boundary for future optional providers. No provider is installed by this module."""

from typing import Protocol

from apple_tv_agent.observation.models import ScreenBinding, ScreenObservation


class ScreenProvider(Protocol):
    async def observe(self, binding: ScreenBinding, *, deadline: float) -> ScreenObservation:
        """Capture once within a shared loop.time() deadline, including cleanup.

        Resolve a trusted LG registration by UUID and verify TLS before loading
        its credential. Check input before and after acquisition. Decode and
        validate the complete bounded image before creating the result. Remove
        partial artifacts on every failure/cancellation and close connections.
        Implementations translate failures into the application's fixed errors;
        raw SSAP errors, client keys and image URLs must never escape this boundary.
        """
        ...

    async def discard(self, observation: ScreenObservation, *, deadline: float) -> None:
        """Idempotently delete only an artifact owned by this provider.

        Never trust a supplied path alone: look up observation_id in the private
        artifact inventory and reject mismatched ownership. A failed deletion
        must remain visible for cleanup; it is not a successful discard.
        """
        ...
