import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/", re.I)
BAD_PATH_RE = re.compile(r"terms|terms.?conditions|privacy|legal|help|faq|promotion.?terms", re.I)


def http_url(value):
    return str(value or "").startswith(("https://", "http://"))


def is_purchase_url(value):
    if not http_url(value):
        return False
    parsed = urlparse(str(value))
    path = f"{parsed.path} {parsed.query}"
    if BAD_PATH_RE.search(path) and not SHOP_PATH_RE.search(path):
        return False
    return bool(SHOP_PATH_RE.search(path))


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("news.json is not a list")

    errors = []
    code_count = 0
    seo_count = 0

    for item in data:
        code = str(item.get("code") or "").strip()
        promotion = str(item.get("promotion_url") or item.get("url") or "").strip()
        if code:
            code_count += 1
            if not is_purchase_url(promotion):
                errors.append(f"CODE {item.get('merchant')} {code}: non-purchase destination {promotion}")
        else:
            seo_count += 1
            if not http_url(promotion):
                errors.append(f"SEO {item.get('merchant')}: missing promotion destination")

    if errors:
        print(f"OFFER LINK VALIDATION FAILED: errors={len(errors)} code_offers={code_count} seo_offers={seo_count}")
        for error in errors[:40]:
            print(error)
        raise SystemExit(1)

    print(f"OFFER LINK VALIDATION OK: code_offers={code_count} seo_offers={seo_count}")


if __name__ == "__main__":
    main()
