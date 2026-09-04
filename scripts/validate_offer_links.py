import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
BAD_PATH_RE = re.compile(r"terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions|returns|support|promo.?terms|product-advice", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)


def host(value):
    return (urlparse(str(value or "")).hostname or "").lower().removeprefix("www.")


def is_purchase_url(value):
    if not str(value or "").startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(value))
    path = f"{parsed.path} {parsed.query}"
    if BAD_PATH_RE.search(path) and not SHOP_PATH_RE.search(path):
        return False
    return bool(SHOP_PATH_RE.search(path) or COMMERCE_HOST_RE.search((parsed.hostname or "").lower()))


def same_official_domain(source, destination):
    src, dst = host(source), host(destination)
    if not src or not dst:
        return False
    return dst == src or dst.endswith("." + src) or src.endswith("." + dst)


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("news.json is not a list")
    errors = []
    for item in data:
        destination = str(item.get("final_purchase_url") or "").strip()
        source = str(item.get("source_url") or "").strip()
        if not is_purchase_url(destination):
            errors.append(f"{item.get('merchant')} {item.get('code') or 'DEAL'}: non-purchase destination {destination}")
            continue
        if item.get("promotion_url") != destination or item.get("url") != destination:
            errors.append(f"{item.get('merchant')}: duplicate destination fields are inconsistent")
        if not source.startswith(("https://", "http://")):
            errors.append(f"{item.get('merchant')}: invalid source_url")
        elif not same_official_domain(source, destination):
            errors.append(f"{item.get('merchant')} {item.get('code') or 'DEAL'}: destination leaves source's official domain: {destination}")
        if source and destination == source:
            errors.append(f"{item.get('merchant')} {item.get('code') or 'DEAL'}: final_purchase_url is still the program/source page")
    if errors:
        print(f"OFFER LINK VALIDATION FAILED: errors={len(errors)}")
        for error in errors[:100]:
            print(error)
        raise SystemExit(1)
    print(f"OFFER LINK VALIDATION OK: offers={len(data)}; destinations are purchase-capable and remain on the official source domain")


if __name__ == "__main__":
    main()
