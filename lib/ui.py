"""Shared Streamlit widgets."""

import html

import pandas as pd
import streamlit as st

from lib import ai, db, media
from lib.pipeline import get_profile

CSS = """
<style>
.ad-meta {font-size: 0.8rem; color: #6b7280; margin: 0.15rem 0;}
.ad-title {font-weight: 600; margin: 0.25rem 0 0.1rem 0;}
.ad-body {font-size: 0.85rem; white-space: pre-wrap; max-height: 9.5em; overflow: hidden;}
.pill {display:inline-block; padding: 0.05rem 0.5rem; border-radius: 999px; font-size: 0.75rem;
       background: rgba(127,127,127,0.15); margin-right: 0.25rem;}
</style>
"""


def setup(title: str):
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)


def _val(row, key):
    """Row value, with pandas NaN normalised to None (NaN is truthy, so `or ""` misses it)."""
    v = row.get(key)
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def txt(row, key, default="") -> str:
    """Always a string — safe to slice and concatenate even when the column is NULL/NaN."""
    v = _val(row, key)
    return default if v is None else str(v)


def show_media(row, thumb_b64=None):
    video = _val(row, "video_url")
    image = _val(row, "image_url") or _val(row, "video_preview_url")
    if thumb_b64 and not video:
        st.image(media.data_uri(thumb_b64), width="stretch")
    elif video:
        st.video(video)
    elif image:
        st.image(image, width="stretch")
    elif thumb_b64:
        st.image(media.data_uri(thumb_b64), width="stretch")
    else:
        st.caption("No preview available")


def save_to_swipe(row):
    thumb = media.thumbnail_b64(_val(row, "image_url") or _val(row, "video_preview_url"))
    db.add_swipe(row["ad_archive_id"], thumb_b64=thumb)


def run_analysis(ad_id):
    ad = db.get_ad(ad_id)
    with st.spinner("Claude is breaking this ad down…"):
        result = ai.analyze_ad(ad, get_profile())
    db.save_analysis(ad_id, result)
    return result


def ad_card(row, saved_ids: set, key_prefix: str = "feed"):
    ad_id = row["ad_archive_id"]
    with st.container(border=True):
        show_media(row)
        label = _val(row, "label") or ""
        days = int(_val(row, "days_running") or 0)
        st.markdown(
            f"<span class='pill'>{html.escape(label)}</span>"
            f"<span class='pill'>{days}d</span>"
            f"<span class='pill'>{html.escape(str(_val(row, 'display_format') or ''))}</span>"
            f"<span class='pill'>score {int(_val(row, 'score') or 0)}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"<div class='ad-meta'>{html.escape(str(row.get('page_name') or ''))} · since "
                    f"{row.get('start_date')} · variants {int(_val(row, 'collation_count') or 1)} · "
                    f"copies {int(_val(row, 'copies') or 1)}</div>", unsafe_allow_html=True)
        if _val(row, "title"):
            st.markdown(f"<div class='ad-title'>{html.escape(row['title'])}</div>", unsafe_allow_html=True)
        if _val(row, "body"):
            st.markdown(f"<div class='ad-body'>{html.escape(row['body'])}</div>", unsafe_allow_html=True)
        if _val(row, "angle"):
            st.caption(f"🧠 {row['angle']} · {row.get('creative_format')} · {row.get('awareness')}")

        c1, c2, c3 = st.columns(3)
        if ad_id in saved_ids:
            c1.button("⭐ Saved", key=f"{key_prefix}-s-{ad_id}", disabled=True, width="stretch")
        elif c1.button("☆ Save", key=f"{key_prefix}-s-{ad_id}", width="stretch"):
            save_to_swipe(row)
            st.toast("Saved to swipe file")
            st.rerun()
        if c2.button("🧠 Analyse", key=f"{key_prefix}-a-{ad_id}", width="stretch",
                     disabled=not ai.enabled(), help=None if ai.enabled() else "Add ANTHROPIC_API_KEY"):
            try:
                run_analysis(ad_id)
                st.rerun()
            except ai.AIError as e:
                st.error(str(e))
        if _val(row, "ad_library_url"):
            c3.link_button("Library ↗", row["ad_library_url"], width="stretch")


def ad_grid(df: pd.DataFrame, key_prefix: str, per_page: int = 24, cols: int = 3):
    if df.empty:
        st.info("No ads match these filters yet.")
        return
    saved = db.swipe_ids()
    pages = max((len(df) - 1) // per_page + 1, 1)
    page = st.number_input(f"Page (of {pages})", 1, pages, 1, key=f"{key_prefix}-page") if pages > 1 else 1
    chunk = df.iloc[(page - 1) * per_page: page * per_page]
    columns = st.columns(cols)
    for i, (_, row) in enumerate(chunk.iterrows()):
        with columns[i % cols]:
            ad_card(row.to_dict(), saved, key_prefix)
