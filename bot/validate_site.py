import json
import re
from pathlib import Path
from urllib.parse import urlparse

from catalog_utils import CATALOG, brand_slug, canonicalize_item, is_active_offer, resolve_brand

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SITEMAP_BRANDS = ROOT / "sitemap-brands.xml"
CATEGORY_SLUGS = {"Fashion":"fashion","Beauty":"beauty","Gaming":"gaming","Consumer":"consumer","Home & Living":"home-living","Sports & Outdoor":"sports-outdoor","Food & Grocery":"food-grocery","Travel & Hotels":"travel-hotels","Software & Digital Services":"software-digital-services","Baby, Kids & Family":"baby-kids-family","Automotive & Accessories":"automotive-accessories","Books, Education & Media":"books-education-media"}


def load_items():
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        raise SystemExit(f"VALIDATION ERROR: cannot read news.json: {exc}")


def official_destination(item):
    destination = item.get("promotion_url") or item.get("source_url") or item.get("url") or ""
    if not destination:
        return False
    source_domain = str(item.get("source_domain", "")).lower().removeprefix("www.")
    host = urlparse(destination).netloc.lower().removeprefix("www.")
    return bool(host and source_domain and (host == source_domain or host.endswith("." + source_domain)))


def main():
    items = [canonicalize_item(x) for x in load_items() if isinstance(x, dict)]
    active = [x for x in items if is_active_offer(x)]
    errors = []

    slug_owner = {}
    for category, entries in CATALOG.items():
        for entry in entries:
            brand = entry["name"]
            slug = brand_slug(brand)
            owner = slug_owner.get(slug)
            if owner and owner != brand:
                errors.append(f"brand slug collision: {owner!r} and {brand!r} -> {slug}")
            slug_owner[slug] = brand

    active_brands = set()
    for item in active:
        hit = resolve_brand(item.get("merchant"))
        if not hit:
            errors.append(f"active offer has unknown brand: {item.get('merchant')!r}")
            continue
        if item.get("category") != hit["category"]:
            errors.append(f"category mismatch for {hit['name']}: {item.get('category')!r} != {hit['category']}")
        if not (item.get("promotion_url") or item.get("source_url") or item.get("url")):
            errors.append(f"active offer has no destination: {hit['name']}")
        elif not official_destination(item):
            errors.append(f"active offer destination is outside its official source domain: {hit['name']}")
        active_brands.add(hit["name"])

    for category, slug in CATEGORY_SLUGS.items():
        path = ROOT / slug / "index.html"
        if not path.exists():
            errors.append(f"missing category page: {path}")

    sitemap_text = SITEMAP_BRANDS.read_text(encoding="utf-8") if SITEMAP_BRANDS.exists() else ""
    sitemap_urls = set(re.findall(r"<loc>https://deal24h\.net/brand/([^<]+)/</loc>", sitemap_text))
    expected_urls = {brand_slug(b) for b in active_brands}
    if sitemap_urls != expected_urls:
        missing = sorted(expected_urls - sitemap_urls)
        extra = sorted(sitemap_urls - expected_urls)
        if missing:
            errors.append("active brand missing from sitemap-brands: " + ", ".join(missing))
        if extra:
            errors.append("inactive/nonexistent brand present in sitemap-brands: " + ", ".join(extra))

    for category, entries in CATALOG.items():
        for entry in entries:
            brand = entry["name"]
            page = ROOT / "brand" / brand_slug(brand) / "index.html"
            if not page.exists():
                errors.append(f"missing brand page: {brand}")
                continue
            text = page.read_text(encoding="utf-8")
            robots_match = re.search(r'<meta name="robots" content="([^"]+)"', text)
            indexed = brand in active_brands
            if indexed and (not robots_match or robots_match.group(1) != "index,follow"):
                errors.append(f"active brand is not indexable: {brand}")
            if not indexed and (not robots_match or robots_match.group(1) != "noindex,follow"):
                errors.append(f"inactive brand is indexable: {brand}")

    html_files = list((ROOT / "brand").glob("*/index.html")) + [ROOT / slug / "index.html" for slug in CATEGORY_SLUGS.values()]
    for path in html_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for slug in re.findall(r'href="/brand/([^/]+)/"', text):
            target = ROOT / "brand" / slug / "index.html"
            if not target.exists():
                errors.append(f"broken internal brand link in {path.relative_to(ROOT)}: /brand/{slug}/")

    if errors:
        print("SITE VALIDATION FAILED")
        for error in errors:
            print("-", error)
        raise SystemExit(1)

    print(f"SITE VALIDATION PASSED: {len(active)} active offers, {len(active_brands)} active brands, {len(sitemap_urls)} indexed brand URLs")


if __name__ == "__main__":
    main()
