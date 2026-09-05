"""Run the deal collector only against assistant-verified first-party sources.

The research catalog is not an execution allowlist. Only manifests in this
assistant-verified gate are eligible for the bot.
"""
import json
from pathlib import Path

import news_bot

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = [
    ROOT / "data" / "assistant_verified_sources.json",
    ROOT / "data" / "assistant_verified_electronics_additions.json",
    ROOT / "data" / "assistant_verified_beauty_additions.json",
    ROOT / "data" / "assistant_verified_home_additions.json",
]
EXPECTED_CATEGORIES = {"Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"}


def load_verified():
    rows = []
    for path in MANIFESTS:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        part = data.get("verified_sources", [])
        if not isinstance(part, list):
            raise SystemExit(f"ASSISTANT SOURCE GATE FAILED: {path.name} verified_sources must be a list")
        default_category = str(data.get("category", "")).strip()
        for row in part:
            if default_category and "category" not in row:
                row = {**row, "category": default_category}
            rows.append(row)

    out = []
    seen = set()
    for row in rows:
        if row.get("verification_status") != "verified_first_party":
            continue
        category = str(row.get("category", "")).strip()
        if category not in EXPECTED_CATEGORIES:
            continue
        key = (str(row.get("name", "")).strip().lower(), str(row.get("domain", "")).strip().lower())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        out.append({
            "name": f"{row['name']} — Assistant Verified",
            "url": row["official_homepage"],
            "domain": row["domain"],
            "category": category,
            "merchant": row["name"],
        })

    counts = {category: sum(1 for x in out if x["category"] == category) for category in EXPECTED_CATEGORIES}
    if any(counts[c] < 30 for c in EXPECTED_CATEGORIES):
        raise SystemExit(f"ASSISTANT SOURCE GATE FAILED: need 30 verified sources/category, got {counts}")
    return out


def main():
    sources = load_verified()
    news_bot.SOURCES = sources
    print(f"ASSISTANT SOURCE GATE: {len(sources)} verified first-party sources handed to bot")
    for source in sources:
        print(f"  ALLOWED: {source['merchant']} -> {source['domain']}")
    news_bot.main()


if __name__ == "__main__":
    main()
