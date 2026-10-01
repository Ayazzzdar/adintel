"""Thin client for the Apify 'Facebook Ad Library Scraper' actor (~$0.75 per 1,000 ads)."""

from urllib.parse import quote

import requests

from lib import config

ACTOR = "curious_coder~facebook-ads-library-scraper"
API = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"


class ApifyError(RuntimeError):
    pass


def page_library_url(page_id: str, country: str = "ALL", active: str = "active") -> str:
    """Ad Library URL for every ad from one page — works for brands we only know by page_id."""
    return (f"https://www.facebook.com/ads/library/?active_status={active}&ad_type=all"
            f"&country={country}&view_all_page_id={page_id}&search_type=page&media_type=all")


def keyword_search_url(keyword: str, country: str = "ALL", exact: bool = True, active: str = "active") -> str:
    q = quote(f'"{keyword}"' if exact else keyword)
    search_type = "keyword_exact_phrase" if exact else "keyword_unordered"
    return (f"https://www.facebook.com/ads/library/?active_status={active}&ad_type=all"
            f"&country={country}&q={q}&search_type={search_type}&media_type=all")


def run(urls, limit_per_source=50, total=None, active="active", country="ALL",
        sort_by="impressions_desc", period="", timeout=300):
    """Run the actor synchronously and return the raw dataset items (list of dicts)."""
    token = config.get("APIFY_TOKEN")
    if not token:
        raise ApifyError("APIFY_TOKEN is not set (add it to Streamlit secrets).")
    payload = {
        "urls": [{"url": u} for u in urls],
        "limitPerSource": int(limit_per_source),
        "scrapePageAds.activeStatus": active,
        "scrapePageAds.countryCode": country,
        "scrapePageAds.sortBy": sort_by,
    }
    if total:
        payload["count"] = int(total)
    if period:
        payload["scrapePageAds.period"] = period
    resp = requests.post(API, params={"token": token, "timeout": timeout}, json=payload,
                         timeout=timeout + 30)
    if resp.status_code >= 400:
        raise ApifyError(f"Apify returned {resp.status_code}: {resp.text[:300]}")
    items = resp.json()
    # The actor reports "no ads" as an item with an error field — drop those.
    return [it for it in items if isinstance(it, dict) and it.get("ad_archive_id")]
