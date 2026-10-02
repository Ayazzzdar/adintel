import streamlit as st

from lib import ai, apify, db, pipeline, ui
from lib.normalize import normalize
from lib.scoring import enrich

ui.setup("🔭 Discover")

tab_brands, tab_ideas = st.tabs(["🕵️ Find new competitors", "💡 Idea explorer"])

# ---------------------------------------------------------------------------
with tab_brands:
    st.caption("Searches the **whole** Meta Ad Library — not just the brands you track — for "
               "phrases buyers in our niche see, then ranks every advertiser found by how "
               "closely their ads match what we sell. Brands you already track (and ones you've "
               "dismissed) are left out, so what's left is new competitors to consider. "
               "Searches run in small batches and save as they go.")

    keywords = pipeline.get_keywords()
    countries = pipeline.get_countries()
    c1, c2 = st.columns([3, 1])
    kw_text = c1.text_area("Search phrases (one per line)", "\n".join(keywords), height=180)
    countries = c2.multiselect("Countries", ["AU", "US", "GB", "NZ", "CA", "IE", "ALL"], countries)
    per_search = c2.number_input("Ads per search", 10, 200, 40, step=10)
    kw_list = [k.strip() for k in kw_text.splitlines() if k.strip()]
    c2.caption(f"≈ {len(kw_list) * len(countries) * per_search:,} ads max ≈ "
               f"${len(kw_list) * len(countries) * per_search * 0.00075:.2f}")

    b1, b2, b3 = st.columns(3)
    if b1.button("🔭 Run discovery", type="primary", width="stretch"):
        db.set_setting("discovery_keywords", kw_list)
        db.set_setting("discovery_countries", countries)
        status = st.status("Searching the Ad Library…", expanded=True)
        try:
            res = pipeline.run_discovery(kw_list, countries, per_search, progress=status.write)
            status.update(label=f"Found {res['brands']} advertisers across {res['ads']} ads", state="complete")
        except apify.ApifyError as e:
            status.update(label="Failed", state="error")
            st.error(str(e))

    if b2.button("✨ Suggest more phrases (AI)", disabled=not ai.enabled(), width="stretch"):
        ads = db.all_ads()
        copy = ads[ads["brand_id"].notna()]["body"].dropna().drop_duplicates().head(15).tolist() if not ads.empty else []
        try:
            with st.spinner("Thinking of phrases competitors would use…"):
                ideas = ai.suggest_keywords(pipeline.get_profile(), copy, kw_list)
            db.set_setting("discovery_keywords", kw_list + ideas)
            st.success("Added: " + ", ".join(ideas))
            st.rerun()
        except ai.AIError as e:
            st.error(str(e))

    candidates = db.list_discovered("new")
    unchecked = candidates[candidates["ai_verdict"].isna()] if not candidates.empty \
        else candidates
    if b3.button(f"🧠 AI-check next 25 ({len(unchecked)} unchecked)",
                 disabled=not ai.enabled() or unchecked.empty, width="stretch"):
        top = unchecked.head(25)
        try:
            with st.spinner("Classifying advertisers…"):
                verdicts = ai.classify_candidates(top.to_dict("records"), pipeline.get_profile())
            for v in verdicts:
                db.update_discovered(v["page_id"], ai_verdict=v["verdict"], ai_reason=v["reason"])
            st.rerun()
        except ai.AIError as e:
            st.error(str(e))

    st.divider()
    if candidates.empty:
        st.info("No candidates yet — run discovery.")
    else:
        f1, f2 = st.columns(2)
        min_rel = f1.slider("Minimum relevance", 0, 100, 40)
        verdict = f2.multiselect("AI verdict", ["competitor", "adjacent", "irrelevant", "unchecked"],
                                 ["competitor", "adjacent", "unchecked"])
        view = candidates[candidates["relevance"] >= min_rel]
        view = view[view["ai_verdict"].fillna("unchecked").isin(verdict)]
        per_page = 25
        pages = max((len(view) - 1) // per_page + 1, 1)
        page = st.number_input(f"Page (of {pages})", 1, pages, 1, key="cand-page") if pages > 1 else 1
        shown = view.iloc[(page - 1) * per_page: page * per_page]
        first = (page - 1) * per_page + 1
        st.caption(f"{len(view)} candidate brands · showing {first}–{first + len(shown) - 1}, "
                   f"highest relevance first")
        for _, r in shown.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 4, 1.3])
                r = r.to_dict()
                if ui.txt(r, "sample_image"):
                    c1.image(r["sample_image"], width="stretch")
                badge = {"competitor": "🎯 Competitor", "adjacent": "💡 Adjacent / inspo",
                         "irrelevant": "🚫 Irrelevant"}.get(ui.txt(r, "ai_verdict"), "")
                c2.markdown(f"**{r['page_name']}** · relevance {r['relevance']:.0f} · {r['ad_count']} ads · "
                            f"{ui.txt(r, 'landing_domain')} {badge}")
                if ui.txt(r, "ai_reason"):
                    c2.caption(r["ai_reason"])
                c2.caption(f"Found via: {ui.txt(r, 'keywords')}")
                c2.write(" — ".join(p for p in (ui.txt(r, "sample_title"),
                                                ui.txt(r, "sample_body")[:280]) if p))
                if c3.button("➕ Track (competitor)", key=f"tc-{r['page_id']}", width="stretch"):
                    pipeline.track_discovered(r["page_id"], "competitor")
                    st.rerun()
                if c3.button("➕ Track (inspiration)", key=f"ti-{r['page_id']}", width="stretch"):
                    pipeline.track_discovered(r["page_id"], "inspiration")
                    st.rerun()
                if c3.button("Dismiss", key=f"d-{r['page_id']}", width="stretch"):
                    db.update_discovered(r["page_id"], status="dismissed")
                    st.rerun()

# ---------------------------------------------------------------------------
with tab_ideas:
    st.caption("Look outside our niche for angles that already work — e.g. 'gift for mum', "
               "'gift for dad', 'retirement gift', 'nostalgia', '1970s'. Results land in the Ad Feed "
               "under *Discovery searches* and can be saved to the swipe file.")
    c1, c2, c3 = st.columns([3, 1, 1])
    q = c1.text_input("Search phrase", placeholder="gift for dad")
    country = c2.selectbox("Country", ["AU", "US", "GB", "ALL"], index=0)
    n = c3.number_input("Max ads", 10, 200, 40, step=10)
    if st.button("Search", type="primary") and q:
        try:
            with st.spinner("Searching…"):
                items = apify.run([apify.keyword_search_url(q, country, exact=False)], limit_per_source=n)
            rows = [normalize(it, source=f"search:{q}") for it in items]
            db.upsert_ads(rows)
            st.session_state["idea_ids"] = [r["ad_archive_id"] for r in rows]
        except apify.ApifyError as e:
            st.error(str(e))
    ids = st.session_state.get("idea_ids")
    if ids:
        ads = enrich(db.all_ads())
        res = ads[ads["ad_archive_id"].isin(ids)].sort_values("score", ascending=False)
        ui.ad_grid(res, "ideas")
