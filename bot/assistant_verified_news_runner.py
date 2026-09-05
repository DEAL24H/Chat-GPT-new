"""Run the deal collector only against sources personally verified by the assistant.

The research catalog is intentionally not an execution allowlist. A source must be
present in data/assistant_verified_sources.json before the bot can fetch it.
"""
import json
from pathlib import Path

import news_bot

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "data" / "assistant_verified_sources.json"


def load_verified():
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    rows = data.get("verified_sources", [])
    if not isinstance(rows, list):
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: verified_sources must be a list")
    out = []
    seen = set()
    for row in rows:
        if row.get("verification_status") != "verified_first_party":
            continue
        key = (str(row.get("name", "")).strip().lower(), str(row.get("domain", "")).strip().lower())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        out.append({
            "name": f"{row['name']} — Assistant Verified",
            "url": row["official_homepage"],
            "domain": row["domain"],
            "category": row["category"],
            "merchant": row["name"],
        })
    if not out:
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: no assistant-verified sources")
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
