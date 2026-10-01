"""Scheduled job (GitHub Actions): refresh tracked brands, and run discovery on Mondays.

    python -m scripts.refresh            # brands only
    python -m scripts.refresh --discover # brands + discovery
"""

import argparse
import sys
from datetime import date

from lib import db, pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", action="store_true", help="also run keyword discovery")
    parser.add_argument("--limit", type=int, default=50, help="max ads per brand")
    args = parser.parse_args()

    pipeline.seed_defaults()
    brands = db.list_brands(active_only=True).to_dict("records")
    counts = pipeline.refresh_brands(brands, limit_per_brand=args.limit, progress=print)
    for b in brands:
        print(f"  {b['name']}: {counts.get(b['id'], 0)} live ads")

    if args.discover or date.today().weekday() == 0:
        res = pipeline.run_discovery(pipeline.get_keywords(), pipeline.get_countries(), progress=print)
        print(f"Discovery: {res['ads']} ads, {res['brands']} advertisers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
