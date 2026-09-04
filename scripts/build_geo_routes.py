import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.catalog_utils import brand_slug, canonicalize_item, is_active_offer, resolve_brand

DATA = ROOT / "data" / "news.json"
REGIONS = ROOT / "data" / "merchant_regions.json"
MANIFEST = ROOT / "data" / "merchant-routes.json"


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def destination(item):
    return item.get("promotion_url") or item.get("url") or item.get("source_url") or ""


def route_id(item):
    value = str(item.get("id", "")).strip()
    if value:
        return re.sub(r"[^a-zA-Z0-9_-]", "", value)[:80]
    raw = "|".join(str(item.get(k, "")) for k in ("merchant", "title", "promotion_url", "url"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def override_for(overrides, brand):
    brands = overrides.get("brands", {}) if isinstance(overrides, dict) else {}
    return brands.get(normalize(brand), brands.get(brand_slug(brand), {}))


def build_route(item, overrides):
    brand = str(item.get("merchant", "")).strip()
    default = destination(item)
    override = override_for(overrides, brand)
    regions = override.get("regions", {}) if isinstance(override, dict) else {}
    if isinstance(override, dict) and override.get("default"):
        default = str(override["default"])
    regions = {str(k).upper(): str(v) for k, v in regions.items() if str(v).startswith(("https://", "http://"))}
    return {"id": route_id(item), "brand": brand, "default": default, "regions": regions}


def redirect_html(route):
    default = html.escape(route["default"], quote=True)
    payload = json.dumps(route, ensure_ascii=False, separators=(",", ":"))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta http-equiv="refresh" content="0;url={default}"><title>Redirecting | DEAL 24H</title></head><body><p>Redirecting to the official {html.escape(route["brand"])} merchant offer…</p><script>window.DEAL24H_ROUTE={payload};window.location.replace({json.dumps(route["default"])})</script></body></html>'''


def replace_cta_links(routes):
    by_url = {}
    for route in routes.values():
        if route["default"]:
            by_url.setdefault(route["default"], []).append(route["id"])
    html_files = list((ROOT / "brand").glob("*/index.html"))
    html_files += [ROOT / name / "index.html" for name in ("fashion", "beauty", "consumer", "home-living", "food-grocery", "travel-hotels")]
    pattern = re.compile(r'(<a\s+class="cta"\s+href=")([^"]+)(")')
    for path in html_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        def repl(match):
            url = html.unescape(match.group(2))
            candidates = by_url.get(url, [])
            if not candidates:
                return match.group(0)
            return f'{match.group(1)}/go/{candidates[0]}/{match.group(3)}'
        updated = pattern.sub(repl, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def main():
    go_root = ROOT / "go"
    if go_root.exists():
        for child in go_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    raw = load_json(DATA, [])
    overrides = load_json(REGIONS, {"version": 1, "brands": {}})
    items = [canonicalize_item(x) for x in raw if isinstance(x, dict) and is_active_offer(x)]
    routes = {}
    for item in items:
        if not resolve_brand(item.get("merchant")):
            continue
        route = build_route(item, overrides)
        if not route["default"]:
            continue
        routes[route["id"]] = route
        path = ROOT / "go" / route["id"] / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redirect_html(route), encoding="utf-8")
    replace_cta_links(routes)
    manifest = {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "routes": routes}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"GEO ROUTES BUILT: routes={len(routes)}")


if __name__ == "__main__":
    main()
