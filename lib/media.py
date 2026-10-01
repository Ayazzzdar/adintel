"""Ad Library media links expire after a few days, so saved ads keep their own thumbnail copy."""

import base64
import io

import requests
from PIL import Image


def thumbnail_b64(url: str, max_px: int = 640):
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        img.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def data_uri(b64: str) -> str:
    return f"data:image/jpeg;base64,{b64}"
