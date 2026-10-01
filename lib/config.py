"""Secrets/config lookup: environment variables first, then Streamlit secrets."""

import os


def get(name: str, default=None):
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
