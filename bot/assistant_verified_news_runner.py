"""Run the deal collector only against the assistant-verified source gate.

The research catalog is not an execution allowlist. The live gate first verifies
candidate sources in rank order and promotes rank 31+ when a higher-ranked
candidate fails. The bot receives exactly 30 live-verified sources per category.
"""
import json
from pathlib import Path

import news_bot

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "data" / "assistant_verified_source_selection.json"
EXPECTED_CATEGORIES = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]


def load_selection():
    if not SELECTION.exists():
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: run scripts/validate_assistant_source_gate.py first")
    data = json.loads(SELECTION.read_text(encoding="utf-8"))
    sources = data.get("sources", [])
    counts = data.get("counts", {})
    if data.get("total") != 120 or any(counts.get(c) != 30 for c in EXPECTED_CATEGORIES):
        raise SystemExit(f"ASSISTANT SOURCE GATE FAILED: selection counts={counts}")
    if len(sources) != 120:
        raise SystemExit(f"ASSISTANT SOURCE GATE FAILED: selection has {len(sources)} rows")
    out = []
    for row in sources:
        if row.get("verification_status") != "live_verified_first_party":
            raise SystemExit(f"ASSISTANT SOURCE GATE FAILED: unverified row {row}")
        out.append({
            "name": f"{row['name']} — Assistant Verified",
            "url": row["official_homepage"],
            "domain": row["domain"],
            "category": row["category"],
            "merchant": row["merchant"],
        })
    return out, counts


def main():
    sources, counts = load_selection()
    news_bot.SOURCES = sources
    print(f"ASSISTANT SOURCE GATE: {len(sources)} live-verified first-party sources handed to bot; counts={counts}")
    for source in sources:
        print(f"  ALLOWED: {source['merchant']} -> {source['domain']}")
    news_bot.main()


if __name__ == "__main__":
    main()
