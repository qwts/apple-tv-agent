"""Regenerate the checked-in response schema from the installed package models."""

import json
from pathlib import Path

from apple_tv_agent.models import response_schema
from apple_tv_agent.observation.models import observation_schema

if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "schemas" / "response-v1.json"
    target.write_text(
        json.dumps(response_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    (target.parent / "observation-v1.json").write_text(
        json.dumps(observation_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
