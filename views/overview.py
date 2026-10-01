from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import db, ui
from lib.scoring import enrich

ui.setup("📊 Overview")

brands = db.list_brands()
ads = enrich(db.all_ads())
tracked = ads[ads["brand_id"].notna()] if not ads.empty else ads

if tracked.empty:
    st.info("No ads yet. Go to **🏷️ Tracked Brands** and click **Refresh all brands** "
            "to pull your competitors' live ads.")
    st.stop()

week_ago = date.today() - timedelta(days=7)
active = tracked[tracked["is_active"]]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Brands tracked", int(brands["active"].sum()) if not brands.empty else 0)
c2.metric("Live ads", len(active))
c3.metric("New this week", int((tracked["start_date"] >= week_ago).sum()))
c4.metric("Proven winners (60d+)", int((active["days_running"] >= 60).sum()))

st.subheader("Brand scoreboard")
names = brands.set_index("id")["name"].to_dict() if not brands.empty else {}
kinds = brands.set_index("id")["kind"].to_dict() if not brands.empty else {}
rows = []
for bid, grp in tracked.groupby("brand_id"):
    live = grp[grp["is_active"]]
    fmt = live["display_format"].mode()
    rows.append({
        "Brand": names.get(int(bid), grp["page_name"].iloc[0]),
        "Type": kinds.get(int(bid), ""),
        "Live ads": len(live),
        "New (7d)": int((grp["start_date"] >= week_ago).sum()),
        "Switched off": int((~grp["is_active"]).sum()),
        "Proven winners": int((live["days_running"] >= 60).sum()),
        "Longest-running (days)": int(live["days_running"].max()) if len(live) else 0,
        "Main format": fmt.iloc[0] if len(fmt) else "",
        "Video share": f"{(live['display_format'] == 'VIDEO').mean():.0%}" if len(live) else "",
    })
st.dataframe(pd.DataFrame(rows).sort_values("Live ads", ascending=False),
             hide_index=True, width="stretch")

st.subheader("🏆 Top 6 winners right now")
st.caption("Highest score = running longest + most variants + same message re-used across ads.")
own_ids = set(brands.loc[brands["kind"] == "own", "id"].astype(int)) if not brands.empty else set()
others = tracked[~tracked["brand_id"].astype(int).isin(own_ids)]
ui.ad_grid(others[others["is_active"]].sort_values(["score", "days_running"], ascending=False).head(6),
           "ov", per_page=6)

st.subheader("🆕 Launched in the last 7 days")
st.caption("What competitors are testing right now.")
fresh = others[others["start_date"] >= week_ago].sort_values("start_date", ascending=False)
ui.ad_grid(fresh.head(6), "ov-new", per_page=6)
