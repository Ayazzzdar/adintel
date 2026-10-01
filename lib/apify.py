"""Thin client for the Apify 'Facebook Ad Library Scraper' actor (~$0.75 per 1,000 ads)."""

import time
from urllib.parse import quote

import requests

from lib import config

ACTOR = "curious_coder~facebook-ads-library-scraper"
BASE = "https://api.apify.com/v2"


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


TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def _get(url, token, **params):
    resp = requests.get(url, params={"token": token, **params}, timeout=90)
    if resp.status_code >= 400:
        raise ApifyError(f"Apify returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def run(urls, limit_per_source=50, total=None, active="active", country="ALL",
        sort_by="impressions_desc", period="", progress=None, max_wait_minutes=25,
        max_spend_usd=None):
    """Start the actor, wait for it, return the dataset items.

    The run is started asynchronously and polled, so Apify's 5-minute synchronous endpoint
    can't cut a scrape short. Three limits keep it from running away:
      * count          — hard cap on total ads, so the actor stops instead of crawling on
      * maxTotalChargeUsd — hard cap on spend for this run
      * timeout        — generous but finite; the run is also aborted if we stop waiting
    """
    token = config.get("APIFY_TOKEN")
    if not token:
        raise ApifyError("APIFY_TOKEN is not set — paste it on the connect screen.")
    urls = list(urls)
    # Without `count` the actor keeps crawling every URL; cap it at what we actually want.
    total = int(total or limit_per_source * len(urls))
    payload = {
        "urls": [{"url": u} for u in urls],
        "limitPerSource": int(limit_per_source),
        "count": total,
        "scrapePageAds.activeStatus": active,
        "scrapePageAds.countryCode": country,
        "scrapePageAds.sortBy": sort_by,
    }
    if period:
        payload["scrapePageAds.period"] = period

    params = {
        "token": token,
        "timeout": int(max_wait_minutes * 60),
        # ~$0.75 per 1000 ads + start fee; leave headroom but never run away with spend.
        "maxTotalChargeUsd": round(max_spend_usd or max(total * 0.00075 * 2, 1.0), 2),
    }
    resp = requests.post(f"{BASE}/acts/{ACTOR}/runs", params=params, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise ApifyError(f"Apify returned {resp.status_code}: {resp.text[:300]}")
    run_info = resp.json()["data"]
    run_id = run_info["id"]
    if progress:
        progress(f"Apify run {run_id} started — up to {total} ads, "
                 f"max ${params['maxTotalChargeUsd']}.")

    deadline = time.monotonic() + max_wait_minutes * 60
    while run_info["status"] not in TERMINAL:
        if time.monotonic() > deadline:
            # Stop the run so it can't keep scraping (and charging) in the background,
            # then keep whatever it collected.
            try:
                requests.post(f"{BASE}/actor-runs/{run_id}/abort", params={"token": token},
                              timeout=30)
            except requests.RequestException:
                pass
            if progress:
                progress(f"Stopped run {run_id} after {max_wait_minutes} min — "
                         "keeping the ads it collected.")
            break
        # waitForFinish blocks server-side for up to 60s, so this is a cheap long-poll.
        run_info = _get(f"{BASE}/actor-runs/{run_id}", token, waitForFinish=60)["data"]
        if progress and run_info["status"] not in TERMINAL:
            count = (run_info.get("stats") or {}).get("datasetItemCount") or ""
            progress(f"Still scraping… {count and f'{count} ads so far' or ''}".strip())

    items = _get(f"{BASE}/datasets/{run_info['defaultDatasetId']}/items", token,
                 clean="true", format="json")
    if run_info["status"] != "SUCCEEDED":
        if not items:
            raise ApifyError(f"Apify run {run_id} ended with status {run_info['status']}.")
        if progress:
            progress(f"⚠️ Apify run ended with status {run_info['status']} — using the "
                     f"{len(items)} ads it collected.")
    # The actor reports "no ads" as an item with an error field — drop those.
    return [it for it in items if isinstance(it, dict) and it.get("ad_archive_id")]
