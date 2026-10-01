import streamlit as st

from lib import ai, config, db, keys, pipeline, ui

ui.setup("⚙️ Settings")

st.subheader("Connections")
c1, c2, c3 = st.columns(3)
c1.metric("Apify (scraping)", "✅ connected" if config.has("APIFY_TOKEN") else "❌ not connected")
c2.metric("Claude (AI)", "✅ connected" if ai.enabled() else "⚪ not connected")
c3.metric("Database", "Temporary (local)" if db.is_sqlite() else "✅ Supabase")
if db.is_sqlite():
    st.warning("Using a temporary local database — tracked brands, saved ads and briefs can be "
               "lost when the app restarts. Paste a Supabase database URL below to keep them.")

with st.expander("🔑 Update keys", expanded=False):
    st.caption("Keys are kept only in this browser session's memory — never saved.")
    if keys.key_form("settings_keys", "Save keys for this session"):
        st.success("Keys updated")
        st.rerun()

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
