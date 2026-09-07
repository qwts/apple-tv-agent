"""Explicitly unavailable until the later device-service issues are implemented."""

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.ports import CommandResult
from apple_tv_agent.request import Request


class ContractService:
    async def execute(self, request: Request) -> CommandResult:
        raise AgentError(
            ErrorCode.FEATURE_UNAVAILABLE,
            details={"reason": "not_implemented"},
        )
