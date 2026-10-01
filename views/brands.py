import pandas as pd
import streamlit as st

from lib import apify, db, pipeline, ui
from lib.normalize import page_url_from_input

ui.setup("🏷️ Tracked Brands")
st.caption("Brands whose ads we pull every day. Add any Facebook page — competitors, or brands "
           "you just like for inspiration.")

with st.expander("➕ Add a brand", expanded=False):
    with st.form("add_brand", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 3, 1])
        name = c1.text_input("Name", placeholder="Mapiful")
        url = c2.text_input("Facebook page URL or page ID", placeholder="https://www.facebook.com/mapiful/")
        kind = c3.selectbox("Type", ["competitor", "inspiration", "own"])
        if st.form_submit_button("Add brand", type="primary") and url:
            url = url.strip()
            if url.isdigit():
                db.add_brand(name or url, page_id=url, kind=kind)
            else:
                db.add_brand(name or url, fb_url=page_url_from_input(url), kind=kind)
            st.success(f"Added {name or url}. Click Refresh to pull their ads.")

brands = db.list_brands()
if brands.empty:
    st.info("No brands yet.")
    st.stop()

ads = db.all_ads()
counts = ads[ads["is_active"] == True].groupby("brand_id").size() if not ads.empty else pd.Series(dtype=int)  # noqa: E712
brands["live_ads"] = brands["id"].map(counts).fillna(0).astype(int)

limit = st.slider("Max ads per brand per refresh", 10, 200, 50, step=10,
                  help="Apify charges ~$0.75 per 1,000 ads.")
c1, c2 = st.columns(2)


def _refresh(rows):
    status = st.status("Refreshing…", expanded=True)
    try:
        res = pipeline.refresh_brands(rows, limit_per_brand=limit, progress=status.write)
        status.update(label=f"Done — {sum(res.values())} ads pulled", state="complete")
    except apify.ApifyError as e:
        status.update(label="Failed", state="error")
        st.error(str(e))


if c1.button("🔄 Refresh all active brands", type="primary", width="stretch"):
    _refresh(db.list_brands(active_only=True).to_dict("records"))
    st.rerun()

edited = st.data_editor(
    brands[["id", "name", "kind", "active", "live_ads", "fb_url", "page_id", "source", "last_scraped_at", "notes"]],
    column_config={
        "id": None,
        "kind": st.column_config.SelectboxColumn("Type", options=["competitor", "inspiration", "own"]),
        "active": st.column_config.CheckboxColumn("Track"),
        "live_ads": st.column_config.NumberColumn("Live ads", disabled=True),
        "fb_url": st.column_config.LinkColumn("Page"),
        "page_id": st.column_config.TextColumn("Page ID", disabled=True),
        "source": st.column_config.TextColumn("Added via", disabled=True),
        "last_scraped_at": st.column_config.DatetimeColumn("Last refresh", disabled=True, format="D MMM, HH:mm"),
    },
    hide_index=True, width="stretch", key="brand_editor",
)
if c2.button("💾 Save table changes", width="stretch"):
    for _, row in edited.iterrows():
        db.update_brand(int(row["id"]), name=row["name"], kind=row["kind"], active=bool(row["active"]),
                        notes=row["notes"])
    st.success("Saved")
    st.rerun()

st.divider()
c1, c2, c3 = st.columns([3, 1, 1])
choice = c1.selectbox("Single brand", brands["name"].tolist())
row = brands[brands["name"] == choice].iloc[0].to_dict()
if c2.button("Refresh this brand", width="stretch"):
    _refresh([row])
if c3.button("🗑️ Remove brand", width="stretch"):
    db.delete_brand(int(row["id"]))
    st.rerun()
