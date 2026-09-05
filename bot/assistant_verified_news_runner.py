"""Run the deal collector only against assistant-verified first-party sources.

The research catalog is not an execution allowlist. Only manifests in this
assistant-verified gate are eligible for the bot. Backup candidates beyond the
30 selected sources per category are retained for replacement, but are not
handed to the bot unless a selected source is later quarantined.
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
EXPECTED_CATEGORIES = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]


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

    eligible = []
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
        eligible.append(row)

    selected = []
    counts = {}
    for category in EXPECTED_CATEGORIES:
        candidates = [r for r in eligible if str(r.get("category", "")).strip() == category]
        candidates.sort(key=lambda r: (int(r.get("rank", 9999)), str(r.get("name", "")).lower()))
        if len(candidates) < 30:
            counts[category] = len(candidates)
            raise SystemExit(f"ASSISTANT SOURCE GATE FAILED: {category} has only {len(candidates)} verified sources")
        chosen = candidates[:30]
        counts[category] = len(chosen)
        selected.extend(chosen)

    out = []
    for row in selected:
        out.append({
            "name": f"{row['name']} — Assistant Verified",
            "url": row["official_homepage"],
            "domain": row["domain"],
            "category": str(row["category"]).strip(),
            "merchant": row["name"],
        })
    return out, counts


def main():
    sources, counts = load_verified()
    news_bot.SOURCES = sources
    print(f"ASSISTANT SOURCE GATE: {len(sources)} verified first-party sources handed to bot; counts={counts}")
    for source in sources:
        print(f"  ALLOWED: {source['merchant']} -> {source['domain']}")
    news_bot.main()


if __name__ == "__main__":
    main()
