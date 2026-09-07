"""Regenerate the checked-in response schema from the installed package models."""

import json
from pathlib import Path

from apple_tv_agent.models import response_schema

if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "schemas" / "response-v1.json"
    target.write_text(
        json.dumps(response_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
