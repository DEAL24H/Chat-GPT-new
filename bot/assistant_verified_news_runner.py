"""Run the deal collector only against the assistant-verified source gate.

The assistant-verified manifests are the single source of truth for merchant identity.
The bot never re-decides whether a merchant is official. GitHub runtime failures on a
merchant homepage are treated as crawler availability issues, not source-identity
failures.
"""
import json
from pathlib import Path

import news_bot

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "data" / "assistant_verified_source_selection.json"
OUT = ROOT / "data" / "news.json"
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
    if data.get("source_authority") != "assistant_verified_manifests":
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: unexpected source authority")
    if data.get("runtime_source_identity_recheck") is not False:
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: runtime source identity recheck must be disabled")

    out = []
    for row in sources:
        if row.get("verification_status") != "assistant_verified_first_party":
            raise SystemExit(f"ASSISTANT SOURCE GATE FAILED: unverified row {row}")
        out.append({
            "name": f"{row['name']} — Assistant Verified",
            "url": row["official_homepage"],
            "domain": row["domain"],
            "category": row["category"],
            "merchant": row["merchant"],
            "source_verification_status": "assistant_verified_first_party",
            "source_verification_authority": "assistant",
            "source_verification_method": "assistant_research_manifest",
        })
    return out, counts


def apply_source_contract(sources):
    """Make the bot output carry the same source authority as the allowlist."""
    by_merchant = {s["merchant"].casefold(): s for s in sources}
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    if not isinstance(data, list):
        raise SystemExit("SOURCE CONTRACT FAILED: news.json is not a list")

    kept = []
    for item in data:
        merchant = str(item.get("merchant") or "").strip()
        category = str(item.get("category") or "").strip()
        source = by_merchant.get(merchant.casefold())
        if not source:
            continue
        if category not in EXPECTED_CATEGORIES:
            category = source["category"]
        if category != source["category"]:
            raise SystemExit(
                f"SOURCE CONTRACT FAILED: merchant/category mismatch: {merchant} -> {category}; expected {source['category']}"
            )
        item["category"] = source["category"]
        item["country"] = "International"
        item["official_source"] = True
        item["source_domain"] = source["domain"]
        item["source_verification_status"] = "assistant_verified_first_party"
        item["source_verification_authority"] = "assistant"
        item["source_verification_method"] = "assistant_research_manifest"
        item["purchase_url_verification_status"] = None
        item["purchase_url_verification_reason"] = "pending_purchase_destination_validation"
        item["purchase_url_verified_at"] = None
        kept.append(item)

    OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SOURCE CONTRACT: kept={len(kept)} assistant-verified merchant offers across {len(by_merchant)} allowed sources")


def main():
    sources, counts = load_selection()

    # news_bot contains legacy defaults, but the runner replaces both the source list
    # and category classifier so legacy categories cannot leak into TN01 output.
    news_bot.SOURCES = sources
    news_bot.CATEGORIES = {
        "Fashion": ["fashion", "apparel", "clothing", "shoes", "sneaker", "dress", "jeans", "bag", "accessories", "nike", "adidas", "puma", "asos", "zara", "h&m", "uniqlo", "levi", "crocs"],
        "Electronics": ["electronics", "electronic", "laptop", "computer", "phone", "smartphone", "tablet", "tv", "television", "headphone", "monitor", "printer", "camera", "gaming", "apple", "samsung", "sony", "dell", "lenovo", "hp", "logitech", "philips", "nintendo", "bose", "jbl"],
        "Beauty & Personal Care": ["beauty", "cosmetic", "skincare", "makeup", "cosmetics", "sephora", "l'oreal", "loreal", "maybelline", "mac", "nyx", "elf", "cerave", "la roche", "rare beauty", "charlotte tilbury", "glossier", "fenty", "olaplex"],
        "Home & Living": ["home", "living", "household", "kitchen", "appliance", "furniture", "mattress", "decor", "ikea", "dyson", "wayfair", "walmart", "target", "lowe's", "pottery barn", "west elm", "costco"],
    }
    print(f"ASSISTANT SOURCE GATE: {len(sources)} assistant-verified first-party sources handed to bot; counts={counts}")
    for source in sources:
        print(f"  ALLOWED: {source['merchant']} -> {source['domain']}")

    news_bot.main()
    apply_source_contract(sources)


if __name__ == "__main__":
    main()
