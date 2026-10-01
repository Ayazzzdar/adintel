import json

import streamlit as st

from lib import ai, db, ui

ui.setup("🎬 Remix Studio")
st.caption("Your Day Archive versions of winning ads. Copy the Higgsfield hand-off into a Claude "
           "chat that has the Higgsfield connector, paste the finished creative links back here, "
           "then upload to Meta yourself.")

briefs = db.list_briefs()
if briefs.empty:
    st.info("No briefs yet — create one from the ⭐ Swipe File.")
    st.stop()

STATUSES = ["brief", "generating", "ready", "launched"]
show = st.multiselect("Status", STATUSES, ["brief", "generating", "ready"])
view = briefs[briefs["status"].isin(show)] if show else briefs


def _list(value):
    try:
        return json.loads(value or "[]")
    except ValueError:
        return []


for _, row in view.iterrows():
    b = row.to_dict()
    bid = int(b["id"])
    with st.expander(f"#{bid} · {b['concept_name']} · {b['recommended_format']} {b['aspect_ratio']} · "
                     f"inspired by {b['page_name']} · [{b['status']}]", expanded=b["status"] == "brief"):
        ref, main = st.columns([1, 3])
        with ref:
            st.caption("Reference ad")
            ui.show_media(b)
        with main:
            st.markdown(f"**Angle:** {b['angle']}\n\n**Why it works:** {b['why_it_works']}")
            st.markdown("**Hooks**\n" + "\n".join(f"- {h}" for h in _list(b["hooks"])))
            st.markdown("**Headlines**\n" + "\n".join(f"- {h}" for h in _list(b["headlines"])))
            st.markdown("**Primary text**")
            st.code(b["primary_text"], language=None, wrap_lines=True)
            st.markdown(f"**Visual direction:** {b['visual_direction']}")

        t1, t2, t3 = st.tabs(["🤖 Higgsfield hand-off", "🖼️ Image prompt", "🎥 Video prompt"])
        t1.caption("Copy this into Claude (with the Higgsfield connector) to generate the creative.")
        t1.code(ai.higgsfield_handoff(b, bid), language=None, wrap_lines=True)
        t2.code(b["image_prompt"], language=None, wrap_lines=True)
        t3.code(b["video_prompt"], language=None, wrap_lines=True)

        c1, c2, c3 = st.columns([3, 1, 1])
        urls = c1.text_area("Generated creative links (one per line)", b.get("output_urls") or "",
                            key=f"u-{bid}", height=80)
        new_status = c2.selectbox("Status", STATUSES, STATUSES.index(b["status"]), key=f"st-{bid}")
        if c2.button("Save", key=f"sv-{bid}", width="stretch"):
            db.update_brief(bid, output_urls=urls, status=new_status)
            st.rerun()
        if c3.button("🗑️ Delete", key=f"del-{bid}", width="stretch"):
            db.delete_brief(bid)
            st.rerun()
        for link in [u.strip() for u in (b.get("output_urls") or "").splitlines() if u.strip()]:
            if link.lower().split("?")[0].endswith((".mp4", ".mov", ".webm")):
                st.video(link)
            else:
                st.image(link, width=280)

st.divider()
st.subheader("📦 Upload pack")
st.caption("Everything marked *ready* — copy, headlines and creative links — for uploading in Ads Manager.")
ready = briefs[briefs["status"] == "ready"]
if ready.empty:
    st.caption("Nothing marked ready yet.")
else:
    lines = []
    for _, b in ready.iterrows():
        lines += [f"## #{b['id']} {b['concept_name']} ({b['recommended_format']}, {b['aspect_ratio']})",
                  "", "Primary text:", b["primary_text"], "", "Headlines:"]
        lines += [f"- {h}" for h in _list(b["headlines"])]
        lines += ["", "Creative:", b.get("output_urls") or "(none yet)", "", "---", ""]
    pack = "\n".join(lines)
    st.download_button("⬇️ Download upload pack (.md)", pack, "day-archive-upload-pack.md")
    csv = ready[["id", "concept_name", "recommended_format", "aspect_ratio", "primary_text",
                 "headlines", "output_urls"]].to_csv(index=False)
    st.download_button("⬇️ Download as CSV", csv, "day-archive-upload-pack.csv")
