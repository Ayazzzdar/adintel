"""In-app 'Connect' screen: paste API keys before the dashboard starts."""

import requests
import streamlit as st

from lib import config, db


def _check_apify(token: str):
    try:
        r = requests.get("https://api.apify.com/v2/users/me", params={"token": token}, timeout=15)
    except requests.RequestException:
        # Don't lock the user out over a network blip; scraping will report real problems.
        st.warning("Couldn't reach Apify to verify the token — saved it anyway.")
        return None
    if r.status_code == 401:
        return "Apify rejected this token."
    if r.status_code >= 400:
        return f"Apify returned an error ({r.status_code})."
    return None


def _check_claude(key: str):
    if not key.startswith("sk-ant-"):
        return "Claude keys start with 'sk-ant-'."
    return None


def key_form(form_key: str, submit_label: str) -> bool:
    """Render the key fields. Returns True once keys were saved to this session."""
    current = st.session_state.get("api_keys", {})
    with st.form(form_key):
        apify = st.text_input(
            "Apify API token  (required — scrapes the Ad Library)", type="password",
            value=current.get("APIFY_TOKEN", ""), placeholder="apify_api_…",
            help="apify.com → Settings → API & Integrations → Personal API token",
        )
        claude = st.text_input(
            "Claude API key  (optional — AI breakdowns & remix briefs)", type="password",
            value=current.get("ANTHROPIC_API_KEY", ""), placeholder="sk-ant-…",
            help="platform.claude.com → API keys",
        )
        database = st.text_input(
            "Supabase database URL  (optional — keeps your data between sessions)", type="password",
            value=current.get("DATABASE_URL", ""),
            placeholder="postgresql://postgres.xxxx:PASSWORD@aws-0-….pooler.supabase.com:5432/postgres",
            help="Supabase → Connect → Session pooler URI (with your password filled in). "
                 "Leave blank to use a temporary local database.",
        )
        submitted = st.form_submit_button(submit_label, type="primary", width="stretch")

    if not submitted:
        return False
    errors = []
    if not apify:
        errors.append("Apify token is required.")
    elif err := _check_apify(apify.strip()):
        errors.append(err)
    if claude and (err := _check_claude(claude.strip())):
        errors.append(err)
    if database and (err := db.check_connection(database.strip())):
        errors.append(f"Database: {err}")
    if errors:
        for e in errors:
            st.error(e)
        return False
    config.set_session_keys({"APIFY_TOKEN": apify, "ANTHROPIC_API_KEY": claude, "DATABASE_URL": database})
    return True


def connect_gate():
    """Show the connect screen until an Apify token is available (pasted, env or secrets)."""
    if config.has("APIFY_TOKEN"):
        return
    st.title("🔎 Ad Intel")
    st.subheader("Connect your accounts")
    st.caption("Paste your keys to start. They're kept only in this browser session's memory — "
               "never saved to the app, database or GitHub. You'll paste them again after "
               "closing or refreshing the page.")
    if key_form("connect", "Connect & start"):
        st.rerun()
    st.stop()


def sidebar_status():
    """Small key status + 'change keys' control shown on every page."""
    with st.sidebar.expander("🔑 Connections", expanded=False):
        st.write(("✅" if config.has("APIFY_TOKEN") else "❌") + " Apify")
        st.write(("✅" if config.has("ANTHROPIC_API_KEY") else "⚪") + " Claude AI")
        st.write(("✅ Supabase" if config.has("DATABASE_URL") else "⚪ Temporary database"))
        if st.session_state.get("api_keys") and st.button("Change / clear keys", width="stretch"):
            config.clear_session_keys()
            st.rerun()
