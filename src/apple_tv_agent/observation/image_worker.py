"""Isolated JPEG decoder. Bytes enter stdin; only fixed metadata leaves stdout."""

import io
import json
import sys
import warnings

from apple_tv_agent.observation.models import MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS


def decode(raw):
    from PIL import Image, ImageFile

    if (
        not raw
        or len(raw) > MAX_IMAGE_BYTES
        or not raw.startswith(b"\xff\xd8")
        or not raw.endswith(b"\xff\xd9")
    ):
        raise ValueError("Invalid JPEG")
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw), formats=["JPEG"]) as image:
            width, height = image.size
            if width > 8192 or height > 8192 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Image exceeds limits")
            image.verify()
        with Image.open(io.BytesIO(raw), formats=["JPEG"]) as image:
            image.load()
            # A valid nonblack image may be inspected; this does not establish UI/frame freshness.
            gray = image.convert("L")
            black = gray.getextrema()[1] <= 8
            return {"width": width, "height": height, "quality": "black" if black else "usable"}


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_IMAGE_BYTES + 1)
        result = decode(raw)
    except Exception:
        print(json.dumps({"error": "invalid_image"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
