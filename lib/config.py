"""Key lookup, in order: keys pasted into the app this session → environment → Streamlit secrets.

Keys pasted in the app live only in this browser session's memory. They are never written to
disk, the database or the repo — refresh the page and you paste them again.
"""

import os

KEY_NAMES = ("APIFY_TOKEN", "ANTHROPIC_API_KEY", "DATABASE_URL")


def _session_keys():
    try:
        import streamlit as st

        return st.session_state.get("api_keys", {})
    except Exception:
        return {}


def get(name: str, default=None):
    val = _session_keys().get(name)
    if val:
        return val
    val = os.environ.get(name)
    if val:
        return val
    try:
        import streamlit as st

        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return default


def has(name: str) -> bool:
    return bool(get(name))


def set_session_keys(keys: dict):
    import streamlit as st

    st.session_state["api_keys"] = {k: v.strip() for k, v in keys.items() if v and v.strip()}


def clear_session_keys():
    import streamlit as st

    st.session_state.pop("api_keys", None)
