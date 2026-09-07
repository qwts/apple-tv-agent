"""Offline observation boundary checks; no LG dependencies or hardware."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest
from pydantic import ValidationError

from apple_tv_agent.observation.models import ScreenBinding, ScreenObservation, observation_schema


def payload():
    now = datetime(2026, 9, 7, tzinfo=UTC)
    return {
        "observation_id": str(uuid4()),
        "binding": {
            "binding_id": str(uuid4()),
            "apple_tv_id": str(uuid4()),
            "lg_device_id": str(uuid4()),
            "hdmi_input": "com.webos.app.hdmi4",
        },
        "started_at": now,
        "received_at": now + timedelta(seconds=1),
        "expires_at": now + timedelta(seconds=10),
        "observed_input_before": "com.webos.app.hdmi4",
        "observed_input_after": "com.webos.app.hdmi4",
        "quality": "usable",
        "artifact": {
            "path": "/tmp/test-only/frame.jpg",
            "width": 960,
            "height": 540,
            "byte_count": 1024,
            "sha256": "a" * 64,
            "delete_after": now + timedelta(minutes=5),
        },
    }


def test_schema_matches_and_validates_both_host_paths():
    checked = json.loads(
        (Path(__file__).resolve().parents[2] / "schemas/observation-v1.json").read_text()
    )
    assert checked == observation_schema()
    jsonschema.Draft202012Validator.check_schema(checked)
    for path in ("/tmp/test-only/frame.jpg", r"C:\Users\Test User\frame.jpg"):
        data = payload()
        data["artifact"]["path"] = path
        observation = ScreenObservation.model_validate(data)
        jsonschema.validate(observation.model_dump(mode="json"), checked)
        assert observation.eligible_context(observation.binding, now=observation.received_at)


@pytest.mark.parametrize(
    "field,value",
    [
        ("path", "relative.jpg"),
        ("path", "https://192.0.2.1/frame.jpg"),
        ("path", r"\\server\share\frame.jpg"),
        ("path", "/tmp/../frame.jpg"),
        ("path", "/tmp/\nframe.jpg"),
        ("width", True),
        ("width", 0),
        ("width", 8193),
        ("byte_count", 10 * 1024 * 1024 + 1),
        ("sha256", "not-a-hash"),
        ("media_type", "image/png"),
    ],
)
def test_invalid_artifacts(field, value):
    data = payload()
    data["artifact"][field] = value
    with pytest.raises(ValidationError):
        ScreenObservation.model_validate(data)


def test_pixel_limit():
    data = payload()
    data["artifact"].update(width=8192, height=8192)
    with pytest.raises(ValidationError):
        ScreenObservation.model_validate(data)


@pytest.mark.parametrize("quality", ["black", "transitional", "unknown"])
def test_insufficient_images_never_qualify(quality):
    data = payload()
    data["quality"] = quality
    observation = ScreenObservation.model_validate(data)
    assert not observation.eligible_context(observation.binding, now=observation.received_at)


@pytest.mark.parametrize("field", ["observed_input_before", "observed_input_after"])
@pytest.mark.parametrize("value", [None, "com.webos.app.hdmi1", "com.webos.app.home"])
def test_input_changes_or_unknown_context(field, value):
    data = payload()
    data[field] = value
    observation = ScreenObservation.model_validate(data)
    assert not observation.eligible_context(observation.binding, now=observation.received_at)


def test_freshness_and_binding_boundaries():
    observation = ScreenObservation.model_validate(payload())
    assert not observation.eligible_context(observation.binding, now=observation.started_at)
    assert not observation.eligible_context(observation.binding, now=observation.expires_at)
    other = ScreenBinding.model_validate(
        {**observation.binding.model_dump(), "lg_device_id": uuid4()}
    )
    assert not observation.eligible_context(other, now=observation.received_at)
    with pytest.raises(ValueError):
        observation.eligible_context(observation.binding, now=datetime(2026, 9, 7))
    with pytest.raises(ValidationError):
        observation.quality = "usable"


@pytest.mark.parametrize(
    "change", ["old", "reversed", "naive", "early_delete", "unknown_field", "invalid_input"]
)
def test_invalid_results(change):
    data = payload()
    if change == "old":
        data["expires_at"] += timedelta(seconds=1)
    elif change == "reversed":
        data["received_at"] = data["started_at"] - timedelta(seconds=1)
    elif change == "naive":
        data["started_at"] = datetime(2026, 9, 7)
    elif change == "early_delete":
        data["artifact"]["delete_after"] = data["received_at"]
    elif change == "unknown_field":
        data["client_key"] = "synthetic-forbidden-value"
    else:
        data["binding"]["hdmi_input"] = "com.webos.app.home"
    with pytest.raises(ValidationError):
        ScreenObservation.model_validate(data)
