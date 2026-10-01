"""Scraping jobs: refresh tracked brands, and keyword discovery of new brands + ideas."""

import json
import math
from collections import defaultdict

from sqlalchemy import and_, update

from lib import apify, db
from lib.normalize import normalize, page_url_from_input

# ---------------------------------------------------------------------------
# Defaults (editable on the Settings page)
# ---------------------------------------------------------------------------

DEFAULT_BRAND_PROFILE = """Brand: The Day Archive (thedayarchive.com) — Australian brand.
Hero product: "The Birth Day Archive Pack" — a personalised printed keepsake showing what
happened on the day/year someone was born: headline news, prices back then (house, petrol,
bread, stamps, cinema), the #1 song, famous people sharing the birthday, star sign,
population, PM in office, sporting winners (AFL, Bathurst, Australian Open), Oscar winners.
Buyers: mostly women 30-65 buying a gift for a parent, partner or friend's milestone birthday
(18th, 21st, 30th, 40th, 50th, 60th, 70th, 80th+), plus new parents for a baby's birth day.
Positioning: nostalgic, meaningful, personal, "they'll actually love it" gift — not another
generic present. Fast, made-to-order, gift-ready.
Tone: warm, nostalgic, a little playful. Australian spelling (personalised, colour)."""

DEFAULT_KEYWORDS = [
    "day you were born",
    "year you were born",
    "the day you were born",
    "birth year print",
    "personalised birthday gift",
    "milestone birthday gift",
    "birthday keepsake",
    "star map",
    "custom map poster",
    "newspaper from the day",
]

DEFAULT_COUNTRIES = ["AU", "US", "GB"]

NICHE_TERMS = [
    "personalised", "personalized", "keepsake", "gift", "birthday", "born", "birth",
    "print", "poster", "frame", "custom", "star map", "night sky", "map", "history",
    "anniversary", "milestone", "memories", "nostalgi", "wall art", "newspaper", "year",
]
NEGATIVE_TERMS = [
    "supplement", "pain", "joint", "liver", "cholesterol", "weight loss", "drama", "episode",
    "play.google", "apps.apple", "casino", "loan", "crypto", "trading", "detox", "clinic",
    "doctor", "insurance", "probiotic", "gut", "arthritis",
]
GOOD_CATEGORIES = {"gifts", "shopping & retail", "art", "e-commerce website", "printing service",
                   "home decor", "product/service", "brand", "personal blog", "website"}


def get_profile():
    return db.get_setting("brand_profile", DEFAULT_BRAND_PROFILE)


def get_keywords():
    return db.get_setting("discovery_keywords", DEFAULT_KEYWORDS)


def get_countries():
    return db.get_setting("discovery_countries", DEFAULT_COUNTRIES)


OWN_PAGE_ID = "1110400352150378"  # The Day Archive's Facebook page


def seed_defaults():
    """First run: load the starter competitor list."""
    if db.get_setting("seeded"):
        return
    starters = [
        ("Mapiful", "https://www.facebook.com/mapiful/", "competitor"),
        ("A Day In History USA", "https://www.facebook.com/adayinhistoryusa/", "competitor"),
        ("A Day In History UK", "https://www.facebook.com/adayinhistory.co.uk/", "competitor"),
        ("The Night Sky", "https://www.facebook.com/thenightskyio/", "competitor"),
    ]
    for name, url, kind in starters:
        db.add_brand(name, fb_url=url, kind=kind)
    db.set_setting("seeded", True)


# ---------------------------------------------------------------------------
# Brand tracking
# ---------------------------------------------------------------------------

def _brand_source_url(brand) -> str:
    if brand.get("page_id"):
        return apify.page_library_url(brand["page_id"])
    return page_url_from_input(brand["fb_url"])


def refresh_brands(brand_rows, limit_per_brand=50, progress=None):
    """Scrape active ads for each brand. Returns {brand_id: ads_found}."""
    if not brand_rows:
        return {}
    run_start = db.now()
    url_to_brand = {_brand_source_url(b): b for b in brand_rows}
    if progress:
        progress(f"Scraping {len(url_to_brand)} brand(s) via Apify…")
    items = apify.run(list(url_to_brand), limit_per_source=limit_per_brand)

    by_brand = defaultdict(list)
    for it in items:
        brand = url_to_brand.get(it.get("url"))
        if brand is None:  # fall back to matching on page id
            brand = next((b for b in brand_rows if b.get("page_id") == str(it.get("page_id"))), None)
        if brand is not None:
            by_brand[brand["id"]].append(it)

    counts = {}
    for brand in brand_rows:
        found = by_brand.get(brand["id"], [])
        rows = [normalize(it, source="brand", brand_id=brand["id"]) for it in found]
        db.upsert_ads(rows)
        # Attach ads that already existed (e.g. found by discovery first) to this brand.
        if rows:
            db.execute(update(db.ads).where(db.ads.c.ad_archive_id.in_([r["ad_archive_id"] for r in rows]))
                       .values(brand_id=brand["id"]))
        fields = {"last_scraped_at": db.now()}
        if found and not brand.get("page_id"):
            fields["page_id"] = str(found[0].get("page_id"))
        db.update_brand(brand["id"], **fields)
        # Ads we saw before but are gone now have been switched off -> losers (or rotated).
        # Only safe to infer when we didn't hit the scrape limit.
        if len(found) < limit_per_brand:
            db.execute(
                update(db.ads)
                .where(and_(db.ads.c.brand_id == brand["id"], db.ads.c.is_active.is_(True),
                            db.ads.c.last_seen_at < run_start))
                .values(is_active=False, end_date=run_start.date())
            )
        counts[brand["id"]] = len(found)
    return counts


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _ad_text(it) -> str:
    snap = it.get("snapshot") or {}
    body = snap.get("body")
    body = body.get("text") if isinstance(body, dict) else body
    cards = snap.get("cards") or []
    parts = [snap.get("title"), body, snap.get("link_url"), snap.get("caption"),
             snap.get("link_description")]
    if cards:
        parts += [cards[0].get("title"), cards[0].get("body"), cards[0].get("link_url")]
    return " ".join(p for p in parts if p).lower()


def ad_is_relevant(it) -> bool:
    text = _ad_text(it)
    if any(n in text for n in NEGATIVE_TERMS):
        return False
    hits = sum(1 for t in NICHE_TERMS if t in text)
    cats = {c.lower() for c in ((it.get("snapshot") or {}).get("page_categories") or [])}
    return hits >= 2 or (hits >= 1 and bool(cats & GOOD_CATEGORIES))


def score_pages(items, url_to_keyword, exclude_page_ids):
    """Group search results by advertiser and score how likely each is a competitor."""
    pages = defaultdict(list)
    for it in items:
        pid = str(it.get("page_id") or "")
        if pid and pid not in exclude_page_ids:
            pages[pid].append(it)

    rows = []
    ts = db.now()
    for pid, its in pages.items():
        relevant = [it for it in its if ad_is_relevant(it)]
        share = len(relevant) / len(its)
        # Relevance 0-100: mostly "are their ads in our niche", plus a bit for volume.
        relevance = round(share * 80 + min(math.log1p(len(its)) / math.log1p(20), 1) * 20, 1)
        sample = (relevant or its)[0]
        snap = sample.get("snapshot") or {}
        norm = normalize(sample)
        kws = sorted({url_to_keyword.get(it.get("url"), "") for it in its} - {""})
        rows.append({
            "page_id": pid,
            "page_name": sample.get("page_name"),
            "page_url": snap.get("page_profile_uri"),
            "landing_domain": norm["landing_domain"],
            "ad_count": len(its),
            "relevance": relevance,
            "keywords": ", ".join(kws),
            "sample_title": norm["title"],
            "sample_body": (norm["body"] or "")[:600],
            "sample_image": norm["image_url"] or norm["video_preview_url"],
            "page_like_count": snap.get("page_like_count"),
            "status": "new",
            "first_seen_at": ts,
            "last_seen_at": ts,
        })
    return rows


def run_discovery(keywords, countries, per_search=40, progress=None):
    """Search the Ad Library by keyword; save the ads (idea feed) and candidate brands."""
    url_to_keyword = {}
    for kw in keywords:
        for c in countries:
            url_to_keyword[apify.keyword_search_url(kw, c)] = kw
    if progress:
        progress(f"Running {len(url_to_keyword)} Ad Library searches via Apify…")
    items = apify.run(list(url_to_keyword), limit_per_source=per_search)

    db.upsert_ads([normalize(it, source=f"search:{url_to_keyword.get(it.get('url'), '?')}")
                   for it in items])

    tracked = db.list_brands()
    exclude = set(tracked["page_id"].dropna().astype(str)) if not tracked.empty else set()
    exclude.add(OWN_PAGE_ID)  # never suggest ourselves as a competitor
    dismissed = db.list_discovered("dismissed")
    exclude |= set(dismissed["page_id"].astype(str)) if not dismissed.empty else set()
    rows = score_pages(items, url_to_keyword, exclude)
    db.upsert_discovered(rows)
    return {"ads": len(items), "brands": len(rows)}


def track_discovered(page_id, kind="competitor"):
    cand = db.list_discovered()
    row = cand[cand["page_id"] == page_id]
    if row.empty:
        return None
    r = row.iloc[0]
    brand_id = db.add_brand(r["page_name"], fb_url=r["page_url"], page_id=page_id, kind=kind,
                            source="discovered")
    db.update_discovered(page_id, status="tracked")
    # Claim any ads we already have from this page.
    db.execute(update(db.ads).where(db.ads.c.page_id == page_id).values(brand_id=brand_id))
    return brand_id


def platforms_list(value):
    try:
        return json.loads(value or "[]")
    except ValueError:
        return []
