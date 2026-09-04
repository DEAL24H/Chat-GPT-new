import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bot.catalog_utils import canonicalize_item, is_active_offer, resolve_brand

DATA = ROOT / "data" / "news.json"
MANIFEST = ROOT / "data" / "merchant-routes.json"
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
BAD_PATH_RE = re.compile(r"terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions|returns|support|promo.?terms|product-advice", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def is_purchase_url(value):
    if not str(value or "").startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(value))
    path = f"{parsed.path} {parsed.query}"
    if BAD_PATH_RE.search(path) and not SHOP_PATH_RE.search(path):
        return False
    return bool(SHOP_PATH_RE.search(path) or COMMERCE_HOST_RE.search((parsed.hostname or "").lower()))


def route_id(item):
    value = str(item.get("id", "")).strip()
    if value:
        return re.sub(r"[^a-zA-Z0-9_-]", "", value)[:80]
    raw = "|".join(str(item.get(k, "")) for k in ("merchant", "title", "final_purchase_url"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def build_route(item):
    brand = str(item.get("merchant", "")).strip()
    destination = str(item.get("final_purchase_url") or "").strip()
    if not is_purchase_url(destination):
        return None
    return {"id": route_id(item), "brand": brand, "default": destination, "regions": {}}


def redirect_html(route):
    default = html.escape(route["default"], quote=True)
    payload = json.dumps(route, ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta http-equiv="refresh" content="0;url={default}"><title>Redirecting | DEAL 24H</title></head><body><script>window.DEAL24H_ROUTE={payload};window.location.replace({json.dumps(route["default"])})</script></body></html>'''


def replace_cta_links(routes):
    html_files = list((ROOT / "brand").glob("*/index.html"))
    html_files += [ROOT / name / "index.html" for name in ("fashion", "beauty", "consumer", "home-living", "food-grocery", "travel-hotels")]
    article_re = re.compile(r'(<article\s+class="card offer-card">.*?</article>)', re.S)
    cta_re = re.compile(r'(<a\s+class="cta"\s+href=")([^"]+)(")')
    brand_re = re.compile(r'<a\s+class="brandname"\s+href="[^"]+">(.*?)</a>', re.S)
    for path in html_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        def replace_article(article_match):
            article = article_match.group(1)
            brand_match = brand_re.search(article)
            brand = html.unescape(brand_match.group(1)).strip() if brand_match else ""
            def replace_cta(match):
                current = html.unescape(match.group(2))
                for route in routes.values():
                    if normalize(route["brand"]) == normalize(brand) and route["default"] == current:
                        return f'{match.group(1)}/go/{route["id"]}/{match.group(3)}'
                return match.group(0)
            return cta_re.sub(replace_cta, article)
        path.write_text(article_re.sub(replace_article, text), encoding="utf-8")


def main():
    go_root = ROOT / "go"
    if go_root.exists():
        for child in go_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    raw = load_json(DATA, [])
    items = [canonicalize_item(x) for x in raw if isinstance(x, dict) and is_active_offer(x)]
    routes = {}
    skipped = 0
    for item in items:
        if not resolve_brand(item.get("merchant")):
            continue
        route = build_route(item)
        if not route:
            skipped += 1
            continue
        routes[route["id"]] = route
        path = ROOT / "go" / route["id"] / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redirect_html(route), encoding="utf-8")
    replace_cta_links(routes)
    MANIFEST.write_text(json.dumps({"version": 3, "generated_at": datetime.now(timezone.utc).isoformat(), "routes": routes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OFFER-SPECIFIC PURCHASE ROUTES BUILT: routes={len(routes)}, skipped_invalid_destination={skipped}")


if __name__ == "__main__":
    main()
