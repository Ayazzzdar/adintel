import streamlit as st

from lib import ai, config, db, pipeline, ui

ui.setup("⚙️ Settings")

st.subheader("Connections")
c1, c2, c3 = st.columns(3)
c1.metric("Apify (scraping)", "✅ connected" if config.has("APIFY_TOKEN") else "❌ missing APIFY_TOKEN")
c2.metric("Claude (AI)", "✅ connected" if ai.enabled() else "⚠️ missing ANTHROPIC_API_KEY")
c3.metric("Database", "SQLite (local only)" if db.is_sqlite() else "✅ Supabase / Postgres")
if db.is_sqlite():
    st.warning("Using a local SQLite file. On Streamlit Cloud this resets on every redeploy — "
               "add DATABASE_URL (Supabase) to secrets to keep your data.")

st.subheader("Brand profile")
st.caption("Claude reads this every time it analyses an ad or writes a remix brief. The more "
           "specific, the better the output.")
profile = st.text_area("The Day Archive", pipeline.get_profile(), height=300)
if st.button("Save profile", type="primary"):
    db.set_setting("brand_profile", profile)
    st.success("Saved")

st.subheader("Export")
ads = db.all_ads()
if not ads.empty:
    st.download_button("⬇️ All ads (CSV)", ads.to_csv(index=False), "ads.csv")
