import streamlit as st

from lib import ai, db, ui
from lib.scoring import enrich

ui.setup("🔥 Ad Feed & Winners")

ads = enrich(db.all_ads())
if ads.empty:
    st.info("No ads yet — refresh your brands or run a discovery search first.")
    st.stop()

brands = db.list_brands()
brand_names = brands.set_index("id")["name"].to_dict() if not brands.empty else {}
ads["brand"] = ads["brand_id"].map(lambda b: brand_names.get(int(b)) if b == b and b is not None else None)
ads["brand"] = ads["brand"].fillna(ads["page_name"])

with st.sidebar:
    st.header("Filters")
    scope = st.radio("Show ads from", ["Tracked brands", "Discovery searches", "Everything"])
    picked = st.multiselect("Brands", sorted(ads["brand"].dropna().unique()))
    labels = st.multiselect("Status", ["🏆 Proven winner", "📈 Scaling", "✅ Working", "🧪 Testing", "• Running"])
    formats = st.multiselect("Format", sorted(ads["display_format"].dropna().unique()))
    angles = st.multiselect("Angle (after AI analysis)", sorted(ads["angle"].dropna().unique()))
    min_days = st.slider("Running at least (days)", 0, 365, 0)
    live_only = st.checkbox("Live ads only", value=True)
    text = st.text_input("Search copy")
    sort = st.selectbox("Sort by", ["Winner score", "Days running", "Newest", "Variants"])

df = ads
if scope == "Tracked brands":
    df = df[df["brand_id"].notna()]
elif scope == "Discovery searches":
    df = df[df["brand_id"].isna()]
if picked:
    df = df[df["brand"].isin(picked)]
if labels:
    df = df[df["label"].isin(labels)]
if formats:
    df = df[df["display_format"].isin(formats)]
if angles:
    df = df[df["angle"].isin(angles)]
if min_days:
    df = df[df["days_running"] >= min_days]
if live_only:
    df = df[df["is_active"]]
if text:
    mask = df["body"].fillna("").str.contains(text, case=False) | df["title"].fillna("").str.contains(text, case=False)
    df = df[mask]

sort_cols = {"Winner score": ["score", "days_running"], "Days running": ["days_running"],
             "Newest": ["start_date"], "Variants": ["collation_count", "copies"]}[sort]
df = df.sort_values(sort_cols, ascending=False)

c1, c2 = st.columns([3, 1])
c1.caption(f"{len(df)} ads · score = longevity (50) + variants (20) + re-used copy (20) + live (10)")
unanalysed = df[df["angle"].isna()].head(10)
if c2.button(f"🧠 Analyse top {len(unanalysed)} un-analysed", disabled=not ai.enabled() or unanalysed.empty,
             width="stretch"):
    bar = st.progress(0.0)
    for i, ad_id in enumerate(unanalysed["ad_archive_id"]):
        try:
            ui.run_analysis(ad_id)
        except ai.AIError as e:
            st.warning(f"{ad_id}: {e}")
        bar.progress((i + 1) / len(unanalysed))
    st.rerun()

ui.ad_grid(df, "feed")
