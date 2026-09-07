"""Discovery and local registry operations; remaining device services are pending."""

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import AliasData, Command, DefaultData, DevicesData, DiscoveryData
from apple_tv_agent.ports import CommandResult
from apple_tv_agent.request import Request


class ContractService:
    def __init__(self, *, adapter=None, registry=None):
        self.adapter = adapter
        self.registry = registry

    async def execute(self, request: Request) -> CommandResult:
        if request.command == Command.DISCOVER:
            adapter = self.adapter
            if adapter is None:
                from apple_tv_agent.adapters.pyatv_adapter import PyatvAdapter

                adapter = PyatvAdapter()
            devices = await adapter.discover(host=request.host, timeout=request.timeout)
            return CommandResult(None, DiscoveryData(devices=devices))
        if request.command in (
            Command.DEVICES_LIST,
            Command.DEVICES_ALIAS,
            Command.DEVICES_DEFAULT,
        ):
            registry = self.registry
            if registry is None:
                from apple_tv_agent.registry import DeviceRegistry

                registry = DeviceRegistry(timeout=min(5, request.timeout))
            if request.command == Command.DEVICES_LIST:
                data = await registry.snapshot()
                return CommandResult(
                    None,
                    DevicesData(devices=data.devices, default_device_id=data.default_device_id),
                )
            if request.command == Command.DEVICES_ALIAS:
                device = await registry.alias(request.device, request.name)
                return CommandResult(device.device_id, AliasData(aliases=device.aliases))
            device_id = await registry.set_default(request.device)
            return CommandResult(device_id, DefaultData(default_device_id=device_id))
        raise AgentError(ErrorCode.FEATURE_UNAVAILABLE, details={"reason": "not_implemented"})
