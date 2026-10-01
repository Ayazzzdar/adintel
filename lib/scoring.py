"""'Is this ad working?' signals.

Meta's Ad Library hides spend and results, so — like Atria/Superscale — we infer them:
  * Longevity: brands switch off losers fast. An ad still live after 30-60+ days is almost
    certainly profitable.
  * Variants: Meta groups near-identical ads (collation_count). More variants = being scaled.
  * Copies: the same copy re-launched in several ads/ad sets = a proven message being scaled.
"""

from datetime import date

import pandas as pd

from lib.normalize import days_running


def label(row) -> str:
    if row["days_running"] >= 60 and row["is_active"]:
        return "🏆 Proven winner"
    if row["copies"] >= 3 or (row["collation_count"] or 0) >= 3:
        return "📈 Scaling"
    if row["days_running"] >= 30 and row["is_active"]:
        return "✅ Working"
    if row["days_running"] < 14:
        return "🧪 Testing"
    return "• Running"


def enrich(df: pd.DataFrame, today=None) -> pd.DataFrame:
    """Add days_running, copies, score (0-100) and label columns."""
    if df.empty:
        for col in ("days_running", "copies", "score", "label"):
            df[col] = []
        return df
    today = today or date.today()
    df = df.copy()
    for col in ("start_date", "end_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    df["is_active"] = df["is_active"].fillna(False).astype(bool)
    df["collation_count"] = pd.to_numeric(df["collation_count"], errors="coerce").fillna(1).astype(int)
    df["days_running"] = [
        days_running(None if pd.isna(s) else s, None if pd.isna(e) else e, a, today)
        for s, e, a in zip(df["start_date"], df["end_date"], df["is_active"])
    ]
    # Same message re-used across several ads by one page.
    msg_key = df["page_id"].astype(str) + "|" + df["body"].fillna(df["ad_archive_id"]).str[:200]
    df["copies"] = msg_key.map(msg_key.value_counts())

    longevity = (df["days_running"] / 90).clip(upper=1) * 50
    variants = ((df["collation_count"] - 1) / 4).clip(lower=0, upper=1) * 20
    copies = ((df["copies"] - 1) / 5).clip(lower=0, upper=1) * 20
    active = df["is_active"].astype(int) * 10
    df["score"] = (longevity + variants + copies + active).round().astype(int)
    df["label"] = df.apply(label, axis=1)
    return df
