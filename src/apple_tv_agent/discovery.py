"""Identity and selection rules independent of protocol and credential APIs."""

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.models import DeviceRecord, DiscoveredDevice

CANDIDATE_PREFIX = "candidate-"


def identity_matches(known: dict, observed: dict) -> bool:
    shared = known.keys() & observed.keys()
    return bool(shared) and all(known[key] == observed[key] for key in shared)


def identity_overlaps(known: dict, observed: dict) -> bool:
    return any(known[key] == observed[key] for key in known.keys() & observed.keys())


def select_device(devices: list[DeviceRecord], default: str | None, explicit: str | None):
    if explicit is not None:
        matches = [d for d in devices if explicit == d.device_id or explicit in d.aliases]
    elif default is not None:
        matches = [d for d in devices if d.device_id == default]
    else:
        matches = devices
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise AgentError(ErrorCode.DEVICE_NOT_FOUND)
    raise AgentError(
        ErrorCode.DEVICE_AMBIGUOUS,
        details={
            "candidates": [
                {"device_id": d.device_id, "name": d.name, "host": d.last_host} for d in matches
            ]
        },
    )


def resolve_identity(device: DeviceRecord, candidates: list[DiscoveredDevice]):
    """Require consistent protocol identity before any caller may load secrets."""
    overlapping = [c for c in candidates if identity_overlaps(device.identifiers, c.identifiers)]
    if any(not identity_matches(device.identifiers, c.identifiers) for c in overlapping):
        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
    if len(overlapping) > 1:
        raise AgentError(ErrorCode.IDENTITY_MISMATCH, details={"reason": "duplicate_identity"})
    if overlapping:
        return overlapping[0]
    if any(c.host == device.last_host for c in candidates):
        raise AgentError(ErrorCode.IDENTITY_MISMATCH)
    raise AgentError(ErrorCode.DEVICE_NOT_FOUND, details={"reason": "not_discovered"})


def select_pairing_candidate(devices, default, candidates, explicit):
    # A candidate is only eligible through an explicit ID from a current scan.
    if explicit is not None and not any(
        explicit == d.device_id or explicit in d.aliases for d in devices
    ):
        matches = [c for c in candidates if c.candidate_id == explicit]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AgentError(ErrorCode.DEVICE_AMBIGUOUS)
        raise AgentError(ErrorCode.DEVICE_NOT_FOUND)
    return resolve_identity(select_device(devices, default, explicit), candidates)
