"""Bounded read-only sessions, selection and one safe retry without deadline reset."""

import asyncio

from apple_tv_agent.discovery import select_device
from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.locking import device_lock
from apple_tv_agent.models import Command
from apple_tv_agent.pairing import private_protocol_logs
from apple_tv_agent.ports import CommandResult


class SessionService:
    def __init__(self, adapter, registry, vault):
        self.adapter, self.registry, self.vault = adapter, registry, vault

    async def execute(self, request):
        if request.command not in (Command.STATUS, Command.CAPABILITIES):
            raise AgentError(ErrorCode.FEATURE_UNAVAILABLE, details={"reason": "read_only_session"})
        loop = asyncio.get_running_loop()
        end = request.deadline if request.deadline is not None else loop.time() + request.timeout
        reserve = min(1.0, request.timeout * 0.25)
        work_end = end - reserve
        with private_protocol_logs():
            try:
                async with asyncio.timeout_at(end):
                    snapshot = await self.registry.snapshot()
                    selected = select_device(
                        snapshot.devices, snapshot.default_device_id, request.device
                    )
                    async with device_lock(
                        self.registry.path.parent / "locks",
                        selected.device_id,
                        timeout=min(5, max(0, work_end - loop.time())),
                    ):
                        # Pairing/forget may have changed the record while this command waited.
                        snapshot = await self.registry.snapshot()
                        selected = select_device(snapshot.devices, None, selected.device_id)
                        for attempt in range(2):
                            if loop.time() >= work_end:
                                raise TimeoutError
                            session = self.adapter.session()
                            try:
                                async with asyncio.timeout_at(work_end):
                                    await session.connect(selected, self.vault, work_end)
                                    payload = await (
                                        session.status()
                                        if request.command == Command.STATUS
                                        else session.capabilities()
                                    )
                            except AgentError as error:
                                if not (
                                    attempt == 0
                                    and error.code == ErrorCode.NETWORK_ERROR
                                    and error.retryable
                                    and loop.time() < work_end
                                ):
                                    raise
                            else:
                                return CommandResult(selected.device_id, payload)
                            finally:
                                # Cleanup is part of the original deadline, never a fresh timeout.
                                await session.close(max(0, end - loop.time()))
            except asyncio.CancelledError:
                raise AgentError(ErrorCode.NETWORK_ERROR, details={"reason": "canceled"}) from None
            except TimeoutError:
                raise AgentError(ErrorCode.TIMEOUT) from None
