"""Flatten raw Ad Library items into rows for the `ads` table."""

import json
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from lib.db import now

TEMPLATE = re.compile(r"\{\{.*?\}\}")


def _clean(text):
    """Drop catalog placeholders like {{product.name}}."""
    if not text:
        return None
    text = text.strip()
    if TEMPLATE.fullmatch(text):
        return None
    return text or None


def _date(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


def _domain(url):
    if not url:
        return None
    host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def page_url_from_input(text: str) -> str:
    """Accept 'mapiful', 'facebook.com/mapiful', or a full URL; return a canonical page URL."""
    text = text.strip()
    if text.isdigit():
        return text
    if "facebook.com" not in text:
        return f"https://www.facebook.com/{text.strip('/')}/"
    if not text.startswith("http"):
        text = "https://" + text
    return text if text.endswith("/") or "?" in text else text + "/"


def normalize(item: dict, source: str = "brand", brand_id=None) -> dict:
    snap = item.get("snapshot") or {}
    cards = snap.get("cards") or []
    images = snap.get("images") or []
    videos = snap.get("videos") or []
    first_card = cards[0] if cards else {}

    body = _clean((snap.get("body") or {}).get("text") if isinstance(snap.get("body"), dict)
                  else snap.get("body"))
    title = _clean(snap.get("title"))
    # Carousel / catalog (DCO) ads keep their copy and media on the cards.
    body = body or _clean(first_card.get("body"))
    title = title or _clean(first_card.get("title"))

    image = (images[0].get("original_image_url") or images[0].get("resized_image_url")) if images else None
    image = image or first_card.get("original_image_url") or first_card.get("resized_image_url")

    video = video_preview = None
    if videos:
        video = videos[0].get("video_hd_url") or videos[0].get("video_sd_url")
        video_preview = videos[0].get("video_preview_image_url")
    elif first_card.get("video_sd_url") or first_card.get("video_hd_url"):
        video = first_card.get("video_hd_url") or first_card.get("video_sd_url")
        video_preview = first_card.get("video_preview_image_url")

    link = snap.get("link_url") or first_card.get("link_url")
    ts = now()
    return {
        "ad_archive_id": str(item["ad_archive_id"]),
        "page_id": str(item.get("page_id") or snap.get("page_id") or ""),
        "page_name": item.get("page_name") or snap.get("page_name"),
        "brand_id": brand_id,
        "source": source,
        "collation_id": item.get("collation_id"),
        "collation_count": item.get("collation_count"),
        "display_format": snap.get("display_format"),
        "title": title,
        "body": body,
        "cta_text": snap.get("cta_text") or first_card.get("cta_text"),
        "link_url": link,
        "landing_domain": _domain(link),
        "image_url": image,
        "video_url": video,
        "video_preview_url": video_preview,
        "card_count": len(cards),
        "platforms": json.dumps(item.get("publisher_platform") or []),
        "ad_library_url": item.get("ad_library_url"),
        "page_like_count": snap.get("page_like_count"),
        "page_categories": json.dumps(snap.get("page_categories") or []),
        "start_date": _date(item.get("start_date")),
        "end_date": _date(item.get("end_date")),
        "is_active": bool(item.get("is_active")),
        "first_seen_at": ts,
        "last_seen_at": ts,
    }


def days_running(start, end, active, today=None):
    today = today or date.today()
    if start is None:
        return 0
    stop = today if active or end is None else min(end, today)
    return max((stop - start).days, 0)
