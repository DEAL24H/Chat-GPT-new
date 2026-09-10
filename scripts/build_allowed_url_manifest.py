"""Build the fixed root-plus-verified-promo source manifest."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/120_thuong_hieu_kem_trang_goc_va_quoc_gia.xlsx"
OUTPUT = ROOT / "data/allowed_brand_urls.json"
OVERRIDES = ROOT / "data/promo_url_overrides.json"
EXPECTED_CATEGORIES = {"Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"}

def entry(number, merchant, category, market, url, source):
    parsed = urlparse(url)
    return {"id": int(number) if str(number).isdigit() else number, "merchant": merchant, "category": category,
            "market": market, "country": "International" if "gốc" in market.casefold() or "quốc tế" in market.casefold() else market,
            "url": url, "domain": (parsed.hostname or "").lower().removeprefix("www."), "source": source}

def main():
    wb = load_workbook(INPUT, read_only=True, data_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    if not rows or [str(x or "").strip() for x in rows[0]] != ["STT", "Thương hiệu", "Ngành hàng", "Quốc gia / Thị trường", "URL Website"]:
        raise SystemExit("ALLOWLIST INPUT CONTRACT FAILED: unexpected header")
    roots, seen = [], set()
    for raw in rows[1:]:
        values = [str(x or "").strip() for x in raw[:5]]
        if not any(values): continue
        if len(values) != 5 or not all(values[1:]): raise SystemExit("ALLOWLIST INPUT CONTRACT FAILED: incomplete row")
        number, merchant, category, market, url = values
        if category not in EXPECTED_CATEGORIES: raise SystemExit(f"invalid category: {category}")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment: raise SystemExit(f"invalid URL: {url}")
        if merchant in seen: continue
        seen.add(merchant); roots.append(entry(number, merchant, category, market, url, "official_brand_homepage"))
    if len(roots) != 120: raise SystemExit(f"expected 120 root brands, got {len(roots)}")
    root_keys = {(x["merchant"].casefold(), x["url"].rstrip("/").casefold()) for x in roots}
    promo = []
    if OVERRIDES.exists():
        # Overrides are the audited mapping from supplied source URL to promo URL.
        raw_overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        for item in raw_overrides.get("entries", []):
            url = item.get("to_url", "").strip()
            if not url: continue
            merchant, category, market = item["merchant"], item["category"], item["market"]
            root = next((x for x in roots if x["merchant"].casefold() == merchant.casefold()), None)
            if not root: continue
            promo.append(entry(item.get("id", root["id"]), merchant, category, market, url, "audited_official_promo_url"))
    out, keys = list(roots), set(root_keys)
    for item in promo:
        key = (item["merchant"].casefold(), item["url"].rstrip("/").casefold())
        if key not in keys: keys.add(key); out.append(item)
    brands = sorted({x["merchant"] for x in out}, key=str.casefold)
    payload = {"version": 3, "source": INPUT.name, "mode": "root_and_verified_promo_allowlist", "allow_discovery": False,
               "allow_redirect_source_expansion": False, "total_brands": len(brands), "total_urls": len(out), "entries": out}
    if len(brands) != 120: raise SystemExit(f"ALLOWLIST CONTRACT FAILED: brands={len(brands)}")
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ALLOWLIST CREATED: brands={len(brands)} urls={len(out)} roots={len(roots)} verified_promo={len(out)-len(roots)} output={OUTPUT}")

if __name__ == "__main__": main()
