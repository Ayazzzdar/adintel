"""Ad Intel — Meta Ad Library dashboard for The Day Archive.

Run locally:  streamlit run app.py
"""

import streamlit as st

from lib import keys, pipeline

st.set_page_config(page_title="Ad Intel · The Day Archive", page_icon="🔎", layout="wide")


def _password_gate():
    """Optional: set APP_PASSWORD in secrets to keep the dashboard private."""
    from lib import config

    password = config.get("APP_PASSWORD")
    if not password or st.session_state.get("authed"):
        return
    st.title("🔒 Ad Intel")
    entered = st.text_input("Password", type="password")
    if entered and entered == password:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        st.error("Wrong password")
    st.stop()


_password_gate()
keys.connect_gate()
keys.sidebar_status()
pipeline.seed_defaults()

pages = {
    "Research": [
        st.Page("views/overview.py", title="Overview", icon="📊", default=True),
        st.Page("views/feed.py", title="Ad Feed & Winners", icon="🔥"),
        st.Page("views/brands.py", title="Tracked Brands", icon="🏷️"),
        st.Page("views/discover.py", title="Discover", icon="🔭"),
    ],
    "Create": [
        st.Page("views/swipe.py", title="Swipe File", icon="⭐"),
        st.Page("views/studio.py", title="Remix Studio", icon="🎬"),
    ],
    "Setup": [
        st.Page("views/settings.py", title="Settings", icon="⚙️"),
    ],
}
st.navigation(pages).run()
