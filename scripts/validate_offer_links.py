import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
BAD_PATH_RE = re.compile(r"terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions|returns|support|promo.?terms|product-advice", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)


def is_purchase_url(value):
    if not str(value or "").startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(value))
    path = f"{parsed.path} {parsed.query}"
    if BAD_PATH_RE.search(path) and not SHOP_PATH_RE.search(path):
        return False
    return bool(SHOP_PATH_RE.search(path) or COMMERCE_HOST_RE.search((parsed.hostname or "").lower()))


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("news.json is not a list")
    errors = []
    for item in data:
        destination = item.get("final_purchase_url") or item.get("promotion_url") or item.get("url")
        if not is_purchase_url(destination):
            errors.append(f"{item.get('merchant')} {item.get('code') or 'DEAL'}: non-purchase destination {destination}")
        if item.get("promotion_url") != destination or item.get("url") != destination:
            errors.append(f"{item.get('merchant')}: duplicate destination fields are inconsistent")
        if "source_url" in item and not str(item.get("source_url") or "").startswith(("https://", "http://")):
            errors.append(f"{item.get('merchant')}: invalid source_url")
    if errors:
        print(f"OFFER LINK VALIDATION FAILED: errors={len(errors)}")
        for error in errors[:60]:
            print(error)
        raise SystemExit(1)
    print(f"OFFER LINK VALIDATION OK: offers={len(data)}; every CTA destination is purchase-capable")


if __name__ == "__main__":
    main()
