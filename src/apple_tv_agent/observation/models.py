"""Independent v1 screen context contract, separate from Apple TV action outcomes."""

from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

MAX_FRAME_AGE_SECONDS = 10
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ScreenBinding(FrozenModel):
    """User-selected association; HDMI context does not prove physical source identity."""

    binding_id: UUID
    apple_tv_id: UUID
    lg_device_id: UUID
    hdmi_input: Literal[
        "com.webos.app.hdmi1", "com.webos.app.hdmi2", "com.webos.app.hdmi3", "com.webos.app.hdmi4"
    ]


class ImageArtifact(FrozenModel):
    """A fully decoded, validated JPEG in a service-owned private local directory."""

    path: str = Field(min_length=1, max_length=4096)
    media_type: Literal["image/jpeg"] = "image/jpeg"
    width: int = Field(strict=True, gt=0, le=8192)
    height: int = Field(strict=True, gt=0, le=8192)
    byte_count: int = Field(strict=True, gt=0, le=MAX_IMAGE_BYTES)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    delete_after: AwareDatetime

    @model_validator(mode="after")
    def validate_artifact(self):
        if self.width * self.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds pixel limit")
        # Accept either native host's absolute path, but never a network share or URL.
        if (
            any(ord(c) < 32 or ord(c) == 127 for c in self.path)
            or self.path.startswith(("//", "\\\\"))
            or "://" in self.path
            or not (
                PurePosixPath(self.path).is_absolute() or PureWindowsPath(self.path).is_absolute()
            )
            or ".." in PurePosixPath(self.path).parts
            or ".." in PureWindowsPath(self.path).parts
        ):
            raise ValueError("Expected an absolute local artifact path")
        return self


class ScreenObservation(FrozenModel):
    """Successful acquisition, which may still provide insufficient visual context."""

    schema_version: Literal[1] = 1
    provider: Literal["lg-webos"] = "lg-webos"
    observation_id: UUID
    binding: ScreenBinding
    started_at: AwareDatetime
    received_at: AwareDatetime
    expires_at: AwareDatetime
    # Host acquisition times are not a device-provided frame timestamp.
    observed_input_before: str | None = Field(max_length=256)
    observed_input_after: str | None = Field(max_length=256)
    quality: Literal["usable", "black", "transitional", "unknown"]
    artifact: ImageArtifact
    source_frame_time: None = None

    @model_validator(mode="after")
    def validate_timing(self):
        if not self.started_at <= self.received_at < self.expires_at:
            raise ValueError("Invalid observation time order")
        if (self.expires_at - self.started_at).total_seconds() > MAX_FRAME_AGE_SECONDS:
            raise ValueError("Observation validity exceeds freshness limit")
        if self.artifact.delete_after < self.expires_at:
            raise ValueError("Artifact retention ends before observation validity")
        return self

    def eligible_context(self, binding: ScreenBinding, *, now: datetime) -> bool:
        """Context eligibility only; never proof that a requested UI effect occurred."""
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("An aware current timestamp is required")
        return (
            self.binding == binding
            and self.quality == "usable"
            and self.observed_input_before == binding.hdmi_input
            and self.observed_input_after == binding.hdmi_input
            and self.received_at <= now < self.expires_at
        )


def observation_schema():
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **ScreenObservation.model_json_schema(),
    }
