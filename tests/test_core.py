import copy
import os
from datetime import date

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from lib import apify, db, pipeline  # noqa: E402
from lib.normalize import days_running, normalize, page_url_from_input  # noqa: E402
from lib.scoring import enrich  # noqa: E402
from tests.fixtures import DCO_AD, SPAM_AD, VIDEO_AD  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    db._engine_for.cache_clear()
    yield


def test_normalize_video_ad():
    row = normalize(VIDEO_AD, brand_id=1)
    assert row["title"] == "The Perfect Gift 🎁"
    assert row["body"].startswith("What made headlines")
    assert row["video_url"] == "https://video.example/v.mp4"
    assert row["video_preview_url"] == "https://img.example/preview.jpg"
    assert row["landing_domain"] == "adayinhistory.co"
    assert row["start_date"] == date(2025, 12, 19)


def test_normalize_dco_uses_cards_not_placeholders():
    row = normalize(DCO_AD)
    assert row["title"] == "⭐⭐⭐⭐⭐ 2000+ five star reviews!"
    assert "milestone" in row["body"]
    assert row["image_url"] == "https://img.example/orig.jpg"
    assert row["card_count"] == 3


def test_page_url_from_input():
    assert page_url_from_input("mapiful") == "https://www.facebook.com/mapiful/"
    assert page_url_from_input("facebook.com/mapiful") == "https://facebook.com/mapiful/"
    assert page_url_from_input("https://www.facebook.com/mapiful/") == "https://www.facebook.com/mapiful/"


def test_days_running():
    assert days_running(date(2026, 1, 1), date(2026, 9, 30), True, today=date(2026, 3, 1)) == 59
    assert days_running(date(2026, 1, 1), date(2026, 1, 11), False, today=date(2026, 3, 1)) == 10


def test_scoring_labels():
    import pandas as pd
    fresh_scaling = {**copy.deepcopy(DCO_AD), "ad_archive_id": "3", "start_date": 1789776000}  # 20 days
    fresh_test = {**copy.deepcopy(VIDEO_AD), "ad_archive_id": "4", "collation_count": 1,
                  "start_date": 1790208000, "page_id": "x"}  # 5 days
    rows = [normalize(VIDEO_AD), normalize(DCO_AD), normalize(fresh_scaling), normalize(fresh_test)]
    df = enrich(pd.DataFrame(rows), today=date(2026, 10, 1))
    by_id = df.set_index("ad_archive_id")
    assert by_id.loc["1869351803954821", "label"] == "🏆 Proven winner"   # 286 days live
    assert by_id.loc["2027507591518799", "label"] == "🏆 Proven winner"   # 121 days live
    assert by_id.loc["3", "label"] == "📈 Scaling"                        # 3 variants, 20 days
    assert by_id.loc["4", "label"] == "🧪 Testing"
    assert by_id.loc["1869351803954821", "score"] > by_id.loc["4", "score"]
    assert by_id["score"].between(0, 100).all()


def test_relevance_filters_spam():
    assert pipeline.ad_is_relevant(VIDEO_AD)
    assert pipeline.ad_is_relevant(DCO_AD)
    assert not pipeline.ad_is_relevant(SPAM_AD)


def test_refresh_and_discovery_end_to_end(monkeypatch):
    pipeline.seed_defaults()
    brands = db.list_brands(active_only=True).to_dict("records")
    assert len(brands) == 4

    def fake_run(urls, **kw):
        out = []
        for u in urls:
            if "adayinhistoryusa" in u:
                out.append({**copy.deepcopy(VIDEO_AD), "url": u})
            elif "mapiful" in u:
                out.append({**copy.deepcopy(DCO_AD), "url": u})
            elif "search_type=keyword" in u:
                out += [{**copy.deepcopy(SPAM_AD), "url": u},
                        {**copy.deepcopy(VIDEO_AD), "ad_archive_id": "555", "page_id": "777",
                         "page_name": "Birthday Prints Co", "url": u}]
        return out

    monkeypatch.setattr(apify, "run", fake_run)
    counts = pipeline.refresh_brands(brands, limit_per_brand=50)
    assert sum(counts.values()) == 2
    ads = db.all_ads()
    assert set(ads["ad_archive_id"]) == {"1869351803954821", "2027507591518799"}
    mapiful = db.list_brands().set_index("name").loc["Mapiful"]
    assert mapiful["page_id"] == "1483070478613068"

    # Second refresh where Mapiful's ad is gone -> marked switched off.
    monkeypatch.setattr(apify, "run", lambda urls, **kw: [
        {**copy.deepcopy(VIDEO_AD), "url": u} for u in urls if "868316096358585" in u or "adayinhistoryusa" in u])
    pipeline.refresh_brands(db.list_brands(active_only=True).to_dict("records"), limit_per_brand=50)
    ads = db.all_ads().set_index("ad_archive_id")
    assert not ads.loc["2027507591518799", "is_active"]
    assert ads.loc["1869351803954821", "is_active"]

    # Discovery excludes tracked pages and ranks the niche advertiser above spam.
    monkeypatch.setattr(apify, "run", fake_run)
    res = pipeline.run_discovery(["day you were born"], ["AU"])
    cands = db.list_discovered("new").set_index("page_id")
    assert "868316096358585" not in cands.index        # already tracked
    assert cands.loc["777", "relevance"] > cands.loc["890815904120841", "relevance"]
    assert res["brands"] == 2

    brand_id = pipeline.track_discovered("777")
    assert db.list_discovered().set_index("page_id").loc["777", "status"] == "tracked"
    assert db.all_ads().set_index("ad_archive_id").loc["555", "brand_id"] == brand_id


def test_swipe_and_briefs():
    db.upsert_ads([normalize(VIDEO_AD)])
    db.add_swipe("1869351803954821", thumb_b64=None, note="love this")
    assert "1869351803954821" in db.swipe_ids()
    bid = db.add_brief("1869351803954821", {
        "concept_name": "Headlines the day you were born", "angle": "curiosity", "why_it_works": "x",
        "hooks": ["a", "b"], "headlines": ["h1"], "primary_text": "p", "visual_direction": "v",
        "image_prompt": "i", "video_prompt": "vid", "recommended_format": "video", "aspect_ratio": "9:16",
    })
    briefs = db.list_briefs()
    assert briefs.iloc[0]["id"] == bid and briefs.iloc[0]["page_name"] == "A Day In History USA"
    from lib import ai
    handoff = ai.higgsfield_handoff(briefs.iloc[0].to_dict(), bid)
    assert "Higgsfield" in handoff and "vid" in handoff and "9:16" in handoff


def test_settings_roundtrip():
    assert pipeline.get_keywords() == pipeline.DEFAULT_KEYWORDS
    db.set_setting("discovery_keywords", ["a", "b"])
    assert pipeline.get_keywords() == ["a", "b"]


def test_clean_db_url_encodes_special_password():
    url = db.clean_db_url("postgresql://postgres.abc: Pa$s!@1word@aws-0-ap.pooler.supabase.com:5432/postgres ")
    assert url == "postgresql+psycopg2://postgres.abc:Pa%24s%21%401word@aws-0-ap.pooler.supabase.com:5432/postgres"
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    assert parsed.password == "Pa$s!@1word" and parsed.host == "aws-0-ap.pooler.supabase.com"
    # Already-encoded passwords are not double-encoded.
    assert db.clean_db_url(url) == url
    assert db.clean_db_url("sqlite:///x.db") == "sqlite:///x.db"


def test_direct_connection_hint_and_password_hidden():
    assert db.url_hint("postgresql://u:p@db.abc.supabase.co:5432/postgres")
    assert db.url_hint("postgresql://u:p@aws-0-ap.pooler.supabase.com:5432/postgres") is None
    msg = db.check_connection("postgresql://postgres:S3cret!@1@127.0.0.1:1/postgres")
    assert msg and "S3cret" not in msg


def test_own_brand_never_stored_or_suggested(monkeypatch):
    own = {**copy.deepcopy(VIDEO_AD), "ad_archive_id": "own1", "page_id": db.OWN_PAGE_ID,
           "page_name": "The DAY archive"}
    db.upsert_ads([normalize(own), normalize(VIDEO_AD)])
    assert set(db.all_ads()["ad_archive_id"]) == {"1869351803954821"}
    monkeypatch.setattr(apify, "run", lambda urls, **kw: [{**own, "url": u} for u in urls])
    pipeline.run_discovery(["day you were born"], ["AU"])
    assert db.list_discovered().empty


def test_apify_run_polls_with_no_timeout(monkeypatch):
    """The run must be started with timeout=0 and polled until it finishes."""
    from lib import apify
    monkeypatch.setattr(apify.config, "get", lambda name, default=None: "tok")
    posted, polls = {}, {"n": 0}

    class Resp:
        status_code = 201

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_post(url, params=None, json=None, timeout=None):
        posted["params"], posted["json"], posted["url"] = params, json, url
        return Resp({"data": {"id": "RUN1", "status": "RUNNING", "defaultDatasetId": "DS1"}})

    def fake_get(url, params=None, timeout=None):
        if "/actor-runs/" in url:
            polls["n"] += 1
            status = "RUNNING" if polls["n"] < 3 else "SUCCEEDED"
            assert params["waitForFinish"] == 60  # server-side long-poll, not a client timeout
            return Resp({"data": {"id": "RUN1", "status": status, "defaultDatasetId": "DS1",
                                  "stats": {"datasetItemCount": 10 * polls["n"]}}})
        return Resp([VIDEO_AD, {"error": "Ads not found"}])

    monkeypatch.setattr(apify.requests, "post", fake_post)
    monkeypatch.setattr(apify.requests, "get", fake_get)
    notes = []
    items = apify.run(["https://www.facebook.com/mapiful/"], progress=notes.append)

    assert posted["params"]["timeout"] == 25 * 60     # finite run timeout
    assert posted["params"]["maxTotalChargeUsd"] >= 1  # spend cap always set
    assert posted["json"]["count"] == 50               # hard total cap so it can't crawl on
    assert posted["url"].endswith(f"/acts/{apify.ACTOR}/runs")
    assert polls["n"] == 3                            # polled until SUCCEEDED
    assert [i["ad_archive_id"] for i in items] == ["1869351803954821"]  # error rows dropped
    assert any("20 ads so far" in n for n in notes)


def test_apify_run_aborts_after_max_wait(monkeypatch):
    from lib import apify
    monkeypatch.setattr(apify.config, "get", lambda name, default=None: "tok")

    class Resp:
        status_code = 201

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    monkeypatch.setattr(apify.requests, "post", lambda *a, **k: Resp(
        {"data": {"id": "RUN1", "status": "RUNNING", "defaultDatasetId": "DS1"}}))
    monkeypatch.setattr(apify.requests, "get", lambda *a, **k: Resp(
        {"data": {"id": "RUN1", "status": "RUNNING", "defaultDatasetId": "DS1"}}))
    aborted = []
    monkeypatch.setattr(apify.requests, "post", lambda url, **k: (
        aborted.append(url) if url.endswith("/abort") else None) or Resp(
        {"data": {"id": "RUN1", "status": "RUNNING", "defaultDatasetId": "DS1"}}))
    clock = iter([0, 10_000, 20_000])
    monkeypatch.setattr(apify.time, "monotonic", lambda: next(clock))
    notes = []
    items = apify.run(["u"], max_wait_minutes=60, progress=notes.append)
    assert any(u.endswith("/actor-runs/RUN1/abort") for u in aborted)  # run stopped, not left going
    assert items == []
    assert any("Stopped run" in n for n in notes)


def test_discovery_saves_each_batch_before_a_later_failure(monkeypatch):
    """A batch that finished must stay saved even if a later batch dies."""
    pipeline.seed_defaults()
    calls = {"n": 0}

    def flaky_run(urls, **kw):
        calls["n"] += 1
        if calls["n"] > 2:
            raise apify.ApifyError("Apify fell over")
        return [{**copy.deepcopy(VIDEO_AD), "ad_archive_id": f"b{calls['n']}",
                 "page_id": f"p{calls['n']}", "page_name": f"Brand {calls['n']}", "url": urls[0]}]

    monkeypatch.setattr(apify, "run", flaky_run)
    keywords = [f"kw{i}" for i in range(12)]   # 12 searches -> 3 batches of 5
    with pytest.raises(apify.ApifyError):
        pipeline.run_discovery(keywords, ["AU"])
    assert calls["n"] == 3                      # batched, not one giant run
    saved = db.list_discovered()
    assert set(saved["page_id"]) == {"p1", "p2"}   # first two batches persisted
    assert len(db.all_ads()) == 2


def test_null_text_columns_are_safe_to_concatenate():
    """NULL text from the DB arrives as NaN, which is truthy — `or ""` is not enough."""
    import pandas as pd
    from lib import ui
    row = pd.DataFrame([{"sample_title": None, "sample_body": None, "n": 1}]).iloc[0].to_dict()
    assert ui.txt(row, "sample_body") == ""
    assert ui.txt(row, "sample_title")[:280] + " — " + ui.txt(row, "sample_body")[:280] == " — "
    assert ui.txt(row, "missing", "(none yet)") == "(none yet)"
    assert ui.txt(row, "n") == "1"
