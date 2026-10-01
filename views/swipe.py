import streamlit as st

from lib import ai, db, pipeline, ui

ui.setup("⭐ Swipe File")
st.caption("Ads you've saved. Break them down, then turn any of them into a Day Archive remix brief.")

saved = db.list_swipe()
if saved.empty:
    st.info("Nothing saved yet — hit ☆ Save on any ad in the feed.")
    st.stop()

status = st.multiselect("Status", ["saved", "briefed", "done"], ["saved", "briefed"])
saved = saved[saved["status"].isin(status)] if status else saved

for _, row in saved.iterrows():
    r = row.to_dict()
    ad_id = r["ad_archive_id"]
    with st.container(border=True):
        left, right = st.columns([1, 2])
        with left:
            ui.show_media(r, thumb_b64=r.get("thumb_b64"))
            st.caption(f"{r['page_name']} · {r['display_format']} · since {r['start_date']} · "
                       f"{'🟢 live' if r['is_active'] else '⚫ off'}")
            if r.get("ad_library_url"):
                st.link_button("Open in Ad Library ↗", r["ad_library_url"])
        with right:
            if r.get("title"):
                st.markdown(f"**{r['title']}**")
            st.text((r.get("body") or "")[:1200])
            note = st.text_input("Notes", r.get("note") or "", key=f"note-{ad_id}")
            if note != (r.get("note") or ""):
                db.update_swipe_note(ad_id, note)

            breakdown = db.get_analysis(ad_id)
            if breakdown:
                with st.expander("🧠 Breakdown", expanded=False):
                    st.markdown(
                        f"- **Hook:** {breakdown['hook']}\n- **Angle:** {breakdown['angle']}\n"
                        f"- **Format:** {breakdown['creative_format']}\n- **Offer:** {breakdown['offer']}\n"
                        f"- **Awareness:** {breakdown['awareness']}\n- **Emotion:** {breakdown['emotion']}\n"
                        f"- **Audience:** {breakdown['audience']}\n\n**Why it works:** {breakdown['why_it_works']}"
                        f"\n\n**Remix idea:** {breakdown['remix_idea']}")
            elif st.button("🧠 Break it down", key=f"an-{ad_id}", disabled=not ai.enabled()):
                try:
                    ui.run_analysis(ad_id)
                    st.rerun()
                except ai.AIError as e:
                    st.error(str(e))

            extra = st.text_input("Direction for the remix (optional)", key=f"x-{ad_id}",
                                  placeholder="e.g. make it about a 60th birthday for dad, UGC style")
            c1, c2, c3 = st.columns(3)
            if c1.button("🎬 Create remix brief", key=f"rb-{ad_id}", type="primary",
                         disabled=not ai.enabled(), width="stretch"):
                try:
                    with st.spinner("Writing a Day Archive version… (~30-60s)"):
                        brief = ai.remix_brief(db.get_ad(ad_id), breakdown, pipeline.get_profile(), extra)
                    brief["extra_direction"] = extra or None
                    db.add_brief(ad_id, brief)
                    db.set_swipe_status(ad_id, "briefed")
                    st.success("Brief created — open 🎬 Remix Studio.")
                except ai.AIError as e:
                    st.error(str(e))
            if c2.button("✓ Mark done", key=f"dn-{ad_id}", width="stretch"):
                db.set_swipe_status(ad_id, "done")
                st.rerun()
            if c3.button("Remove", key=f"rm-{ad_id}", width="stretch"):
                db.remove_swipe(ad_id)
                st.rerun()
