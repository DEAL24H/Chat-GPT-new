"""Run the deal collector only against the assistant-verified source gate."""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import news_bot

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "data" / "assistant_verified_source_selection.json"
OUT = ROOT / "data" / "news.json"
EXPECTED_CATEGORIES = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]
FETCH_WORKERS = 20
FETCH_TIMEOUT = 8
HEADERS = {"User-Agent": "Deal24H/2.8 (+DEAL24H assistant-verified source collector)"}


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
    if not data.get("unique_merchants_per_category"):
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: selection must guarantee unique merchants per category")
    if not all(x.get("verification_status") == "assistant_verified_first_party" for x in sources):
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: every selected source must be assistant_verified_first_party")
    return sources, counts


def configure_bot_classifier():
    news_bot.CATEGORIES = {
        "Fashion": ["fashion", "apparel", "clothing", "shoes", "sneaker", "dress", "jeans", "bag", "accessories", "nike", "adidas", "puma", "asos", "zara", "h&m", "uniqlo", "levi"],
        "Electronics": ["electronics", "electronic", "laptop", "computer", "phone", "smartphone", "tablet", "tv", "television", "headphone", "monitor", "printer", "camera", "gaming", "apple", "samsung", "sony", "dell", "lenovo", "hp", "logitech", "philips", "nintendo", "bose", "jbl"],
        "Beauty & Personal Care": ["beauty", "cosmetic", "skincare", "makeup", "cosmetics", "sephora", "l'oreal", "loreal", "maybelline", "mac", "nyx", "elf", "cerave", "la roche", "rare beauty", "charlotte tilbury", "glossier", "fenty", "olaplex"],
        "Home & Living": ["home", "living", "household", "kitchen", "appliance", "furniture", "mattress", "decor", "ikea", "dyson", "wayfair", "walmart", "target", "lowe's", "pottery barn", "west elm", "costco"],
    }


def fetch_and_extract(source):
    try:
        source_url = source["official_homepage"]
        runtime_source = dict(source)
        runtime_source["url"] = source_url
        runtime_source["name"] = source.get("name") or source.get("merchant")
        response = requests.get(source_url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        deals = news_bot.extract_deals(response.text, runtime_source)
        return source, deals, None
    except Exception as exc:
        return source, [], f"{type(exc).__name__}: {str(exc)[:180]}"


def apply_source_contract(sources, deals):
    by_merchant = {s["merchant"].casefold(): s for s in sources}
    kept = []
    for item in deals:
        merchant = str(item.get("merchant") or "").strip()
        source = by_merchant.get(merchant.casefold())
        if not source or source["category"] not in EXPECTED_CATEGORIES:
            continue
        item["category"] = source["category"]
        item["country"] = "International"
        item["official_source"] = True
        item["source_domain"] = source["domain"]
        item["source_url"] = source["official_homepage"]
        item["url"] = source["official_homepage"]
        item["source_verification_status"] = "assistant_verified_first_party"
        item["source_verification_authority"] = "assistant"
        item["source_verification_method"] = "assistant_research_manifest"
        item["purchase_url_verification_status"] = None
        item["purchase_url_verification_reason"] = "pending_purchase_destination_resolution"
        item["purchase_url_verified_at"] = None
        kept.append(item)
    OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return kept


def main():
    sources, counts = load_selection()
    configure_bot_classifier()
    print(f"ASSISTANT SOURCE GATE: {len(sources)} unique assistant-verified sources; counts={counts}; parallel_fetch_workers={FETCH_WORKERS}; timeout={FETCH_TIMEOUT}s")

    all_deals = []
    failures = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch_and_extract, source): source for source in sources}
        for future in as_completed(futures):
            source, deals, error = future.result()
            if error:
                failures.append(f"{source['merchant']}: {error}")
                print(f"SOURCE FETCH UNAVAILABLE: {source['merchant']} -> {error}")
                continue
            all_deals.extend(deals)
            print(f"SOURCE FETCH OK: {source['merchant']} -> discovered={len(deals)}")

    kept = apply_source_contract(sources, all_deals)
    print(f"ASSISTANT SOURCE COLLECTION COMPLETE: raw_offers={len(all_deals)} kept={len(kept)} runtime_unavailable_sources={len(failures)}")
    if not kept:
        raise SystemExit("ASSISTANT SOURCE COLLECTION FAILED: no offers were discoverable from the 120 assistant-verified sources")


if __name__ == "__main__":
    main()
