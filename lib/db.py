"""Storage layer. Works with Supabase Postgres (DATABASE_URL) or a local SQLite file."""

import json
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import quote, unquote

import pandas as pd
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Integer, MetaData, String, Table, Text,
    create_engine, delete, select, update,
)

from lib import config

metadata = MetaData()

brands = Table(
    "brands", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("fb_url", Text),
    Column("page_id", String(64)),
    Column("kind", String(32), default="competitor"),     # competitor | inspiration | own
    Column("source", String(32), default="manual"),       # manual | discovered
    Column("active", Boolean, default=True),
    Column("notes", Text),
    Column("added_at", DateTime),
    Column("last_scraped_at", DateTime),
)

ads = Table(
    "ads", metadata,
    Column("ad_archive_id", String(64), primary_key=True),
    Column("page_id", String(64)),
    Column("page_name", String(255)),
    Column("brand_id", Integer),
    Column("source", String(255)),                        # brand | search:<keyword>
    Column("collation_id", String(64)),
    Column("collation_count", Integer),
    Column("display_format", String(32)),
    Column("title", Text),
    Column("body", Text),
    Column("cta_text", String(128)),
    Column("link_url", Text),
    Column("landing_domain", String(255)),
    Column("image_url", Text),
    Column("video_url", Text),
    Column("video_preview_url", Text),
    Column("card_count", Integer),
    Column("platforms", Text),
    Column("ad_library_url", Text),
    Column("page_like_count", Integer),
    Column("page_categories", Text),
    Column("start_date", Date),
    Column("end_date", Date),
    Column("is_active", Boolean),
    Column("first_seen_at", DateTime),
    Column("last_seen_at", DateTime),
)

analysis = Table(
    "analysis", metadata,
    Column("ad_archive_id", String(64), primary_key=True),
    Column("hook", Text),
    Column("angle", String(64)),
    Column("creative_format", String(64)),
    Column("offer", Text),
    Column("awareness", String(64)),
    Column("emotion", String(128)),
    Column("audience", Text),
    Column("why_it_works", Text),
    Column("remix_idea", Text),
    Column("created_at", DateTime),
)

swipe = Table(
    "swipe", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ad_archive_id", String(64), unique=True),
    Column("note", Text),
    Column("status", String(32), default="saved"),        # saved | briefed | done
    Column("thumb_b64", Text),
    Column("saved_at", DateTime),
)

briefs = Table(
    "briefs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ad_archive_id", String(64)),
    Column("concept_name", String(255)),
    Column("angle", Text),
    Column("why_it_works", Text),
    Column("hooks", Text),               # JSON list
    Column("headlines", Text),           # JSON list
    Column("primary_text", Text),
    Column("visual_direction", Text),
    Column("image_prompt", Text),
    Column("video_prompt", Text),
    Column("recommended_format", String(64)),
    Column("aspect_ratio", String(16)),
    Column("extra_direction", Text),
    Column("output_urls", Text),
    Column("status", String(32), default="brief"),  # brief | generating | ready | launched
    Column("created_at", DateTime),
)

discovered = Table(
    "discovered", metadata,
    Column("page_id", String(64), primary_key=True),
    Column("page_name", String(255)),
    Column("page_url", Text),
    Column("landing_domain", String(255)),
    Column("ad_count", Integer),
    Column("relevance", Float),
    Column("ai_verdict", String(32)),    # competitor | adjacent | irrelevant
    Column("ai_reason", Text),
    Column("keywords", Text),
    Column("sample_title", Text),
    Column("sample_body", Text),
    Column("sample_image", Text),
    Column("page_like_count", Integer),
    Column("status", String(32), default="new"),  # new | tracked | dismissed
    Column("first_seen_at", DateTime),
    Column("last_seen_at", DateTime),
)

settings = Table(
    "settings", metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text),
)


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clean_db_url(url: str) -> str:
    """Tidy a pasted Postgres URL: strip spaces and percent-encode the password, so
    passwords containing @ ! # / : etc. work as typed."""
    url = url.strip()
    if url.startswith("sqlite") or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+psycopg2"
    if "@" not in rest:
        return f"{scheme}://{rest}"
    creds, host = rest.rsplit("@", 1)  # the LAST @ separates the password from the host
    user, _, password = creds.partition(":")
    return f"{scheme}://{user.strip()}:{quote(unquote(password.strip()), safe='')}@{host.strip()}"


def url_hint(url: str):
    """Spot the common Supabase mistake: the Direct connection host is IPv6-only, which
    Streamlit Cloud can't reach."""
    host = url.rsplit("@", 1)[-1]
    if host.startswith("db.") and ".supabase.co" in host:
        return ("This is Supabase's *Direct connection* link, which Streamlit Cloud can't reach. "
                "In Supabase click **Connect** → copy the **Session pooler** link instead "
                "(host ends in pooler.supabase.com).")
    return None


@lru_cache(maxsize=4)
def _engine_for(url: str):
    url = clean_db_url(url)
    eng = create_engine(url, pool_pre_ping=True)
    metadata.create_all(eng)
    return eng


def engine():
    """Engine for the current DATABASE_URL (which may be pasted in-app per session)."""
    return _engine_for(config.get("DATABASE_URL") or "sqlite:///ad_intel.db")


def check_connection(url: str):
    """Return None if the database URL works, else an error message."""
    try:
        with _engine_for(url).connect():
            return None
    except Exception as e:  # noqa: BLE001 - show any driver error to the user
        _engine_for.cache_clear()
        msg = str(e).splitlines()[0][:300]
        # Never echo the password back on screen.
        _, _, pwd = url.rsplit("@", 1)[0].partition("://")[2].partition(":")
        if pwd:
            msg = msg.replace(pwd, "•••").replace(quote(unquote(pwd), safe=""), "•••")
        hint = url_hint(url)
        return f"{msg}\n\n{hint}" if hint else msg


def is_sqlite():
    return engine().dialect.name == "sqlite"


def _insert(table):
    if is_sqlite():
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    return insert(table)


def upsert(table, rows, key, keep_on_update=()):
    """Insert rows; on key conflict update every column except key + keep_on_update."""
    if not rows:
        return
    with engine().begin() as conn:
        for row in rows:
            stmt = _insert(table).values(**row)
            cols = {c: stmt.excluded[c] for c in row if c != key and c not in keep_on_update}
            stmt = stmt.on_conflict_do_update(index_elements=[key], set_=cols) if cols \
                else stmt.on_conflict_do_nothing(index_elements=[key])
            conn.execute(stmt)


def df(query) -> pd.DataFrame:
    with engine().connect() as conn:
        return pd.read_sql(query, conn)


def execute(stmt):
    with engine().begin() as conn:
        return conn.execute(stmt)


# ---------- settings ----------

def get_setting(key, default=None):
    with engine().connect() as conn:
        row = conn.execute(select(settings.c.value).where(settings.c.key == key)).first()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return row[0]


def set_setting(key, value):
    upsert(settings, [{"key": key, "value": json.dumps(value)}], "key")


# ---------- brands ----------

def list_brands(active_only=False) -> pd.DataFrame:
    q = select(brands).order_by(brands.c.kind, brands.c.name)
    if active_only:
        q = q.where(brands.c.active.is_(True))
    out = df(q)
    # NaN -> None so callers can use plain truthiness checks on optional columns.
    return out.astype(object).where(out.notna(), None)


def add_brand(name, fb_url=None, page_id=None, kind="competitor", source="manual", notes=None):
    with engine().begin() as conn:
        if page_id:
            existing = conn.execute(select(brands.c.id).where(brands.c.page_id == page_id)).first()
            if existing:
                return existing[0]
        if fb_url:
            existing = conn.execute(select(brands.c.id).where(brands.c.fb_url == fb_url)).first()
            if existing:
                return existing[0]
        res = conn.execute(brands.insert().values(
            name=name, fb_url=fb_url, page_id=page_id, kind=kind, source=source,
            active=True, notes=notes, added_at=now(),
        ))
        return res.inserted_primary_key[0]


def update_brand(brand_id, **fields):
    execute(update(brands).where(brands.c.id == brand_id).values(**fields))


def delete_brand(brand_id):
    execute(delete(brands).where(brands.c.id == brand_id))


# ---------- ads ----------

# The Day Archive's own Facebook page: never stored, shown or suggested as a competitor.
OWN_PAGE_ID = "1110400352150378"


def upsert_ads(rows):
    rows = [r for r in rows if str(r.get("page_id")) != OWN_PAGE_ID]
    upsert(ads, rows, "ad_archive_id", keep_on_update=("first_seen_at", "brand_id"))


def all_ads() -> pd.DataFrame:
    q = select(ads, analysis.c.angle, analysis.c.creative_format, analysis.c.hook,
               analysis.c.awareness, analysis.c.why_it_works) \
        .select_from(ads.outerjoin(analysis, ads.c.ad_archive_id == analysis.c.ad_archive_id)) \
        .where(ads.c.page_id != OWN_PAGE_ID)
    return df(q)


def get_ad(ad_id):
    with engine().connect() as conn:
        row = conn.execute(select(ads).where(ads.c.ad_archive_id == ad_id)).mappings().first()
    return dict(row) if row else None


def get_analysis(ad_id):
    with engine().connect() as conn:
        row = conn.execute(select(analysis).where(analysis.c.ad_archive_id == ad_id)).mappings().first()
    return dict(row) if row else None


def save_analysis(ad_id, data: dict):
    upsert(analysis, [{"ad_archive_id": ad_id, **data, "created_at": now()}], "ad_archive_id")


# ---------- swipe file ----------

def swipe_ids() -> set:
    with engine().connect() as conn:
        return {r[0] for r in conn.execute(select(swipe.c.ad_archive_id))}


def add_swipe(ad_id, thumb_b64=None, note=None):
    upsert(swipe, [{"ad_archive_id": ad_id, "thumb_b64": thumb_b64, "note": note,
                    "status": "saved", "saved_at": now()}], "ad_archive_id",
           keep_on_update=("status", "saved_at"))


def remove_swipe(ad_id):
    execute(delete(swipe).where(swipe.c.ad_archive_id == ad_id))


def list_swipe() -> pd.DataFrame:
    q = select(swipe, ads.c.page_name, ads.c.title, ads.c.body, ads.c.display_format,
               ads.c.image_url, ads.c.video_url, ads.c.video_preview_url, ads.c.start_date,
               ads.c.end_date, ads.c.is_active, ads.c.ad_library_url, ads.c.link_url) \
        .select_from(swipe.join(ads, swipe.c.ad_archive_id == ads.c.ad_archive_id)) \
        .order_by(swipe.c.saved_at.desc())
    return df(q)


def set_swipe_status(ad_id, status):
    execute(update(swipe).where(swipe.c.ad_archive_id == ad_id).values(status=status))


def update_swipe_note(ad_id, note):
    execute(update(swipe).where(swipe.c.ad_archive_id == ad_id).values(note=note))


# ---------- briefs ----------

def add_brief(ad_id, data: dict) -> int:
    row = dict(data)
    for k in ("hooks", "headlines"):
        if isinstance(row.get(k), list):
            row[k] = json.dumps(row[k])
    with engine().begin() as conn:
        res = conn.execute(briefs.insert().values(ad_archive_id=ad_id, status="brief",
                                                  created_at=now(), **row))
        return res.inserted_primary_key[0]


def list_briefs() -> pd.DataFrame:
    q = select(briefs, ads.c.page_name, ads.c.image_url, ads.c.video_preview_url) \
        .select_from(briefs.outerjoin(ads, briefs.c.ad_archive_id == ads.c.ad_archive_id)) \
        .order_by(briefs.c.created_at.desc())
    return df(q)


def update_brief(brief_id, **fields):
    execute(update(briefs).where(briefs.c.id == brief_id).values(**fields))


def delete_brief(brief_id):
    execute(delete(briefs).where(briefs.c.id == brief_id))


# ---------- discovery ----------

def upsert_discovered(rows):
    upsert(discovered, rows, "page_id", keep_on_update=("status", "first_seen_at", "ai_verdict", "ai_reason"))


def list_discovered(status=None) -> pd.DataFrame:
    q = select(discovered).order_by(discovered.c.relevance.desc(), discovered.c.ad_count.desc())
    if status:
        q = q.where(discovered.c.status == status)
    return df(q)


def update_discovered(page_id, **fields):
    execute(update(discovered).where(discovered.c.page_id == page_id).values(**fields))
