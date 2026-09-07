"""Synthetic metadata fixtures for skill walkthroughs; no real image, TV or vault."""

import sys
from datetime import UTC, datetime, timedelta

from apple_tv_agent.errors import AgentError, ErrorCode
from apple_tv_agent.observation import cli
from apple_tv_agent.observation.models import ScreenObservation

BINDING = "00000000-0000-0000-0000-000000000001"
scenario = sys.argv[1]


async def fixture(args):
    if scenario == "input-error":
        raise AgentError(ErrorCode.FEATURE_UNAVAILABLE, details={"reason": "input_mismatch"})
    now = datetime.now(UTC)
    start = now - timedelta(seconds=30 if scenario == "expired" else 1)
    return ScreenObservation.model_validate(
        {
            "observation_id": "00000000-0000-0000-0000-000000000002",
            "binding": {
                "binding_id": BINDING,
                "apple_tv_id": "00000000-0000-0000-0000-000000000003",
                "lg_device_id": "00000000-0000-0000-0000-000000000004",
                "hdmi_input": "com.webos.app.hdmi4",
            },
            "started_at": start,
            "received_at": start + timedelta(milliseconds=100),
            "expires_at": start + timedelta(seconds=10),
            "observed_input_before": "com.webos.app.hdmi4",
            "observed_input_after": "com.webos.app.hdmi1"
            if scenario == "wrong-input"
            else "com.webos.app.hdmi4",
            "quality": "black" if scenario == "black" else "usable",
            "artifact": {
                "path": "/synthetic-only/no-image.jpg",
                "width": 8,
                "height": 8,
                "byte_count": 100,
                "sha256": "a" * 64,
                "delete_after": now + timedelta(minutes=5),
            },
        }
    ).model_dump(mode="json")


cli.dispatch = fixture
cli.require_decoder = lambda: None
raise SystemExit(cli.main(sys.argv[2:]))
