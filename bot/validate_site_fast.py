import json
import re
from pathlib import Path
from urllib.parse import urlparse

from catalog_utils import CATALOG, brand_slug, canonicalize_item, is_active_offer, resolve_brand

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SITEMAP_BRANDS = ROOT / "sitemap-brands.xml"
CATEGORY_SLUGS = {
    "Fashion": "fashion",
    "Electronics": "electronics",
    "Beauty & Personal Care": "beauty-personal-care",
    "Home & Living": "home-living",
}


def load_items():
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        raise SystemExit(f"VALIDATION ERROR: cannot read news.json: {exc}")


def host(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else "https://" + raw)
    return (parsed.hostname or "").lower().removeprefix("www.")


def same_domain(destination, domain):
    dst, src = host(destination), host(domain)
    return bool(dst and src and (dst == src or dst.endswith("." + src)))


def official_destination(item, catalog_entry):
    destination = (
        item.get("final_purchase_url")
        or item.get("promotion_url")
        or item.get("source_url")
        or item.get("url")
        or ""
    )
    if not destination:
        return False
    return same_domain(destination, catalog_entry.get("domain", ""))


def main():
    items = [canonicalize_item(x) for x in load_items() if isinstance(x, dict)]
    active = [x for x in items if is_active_offer(x)]
    errors = []

    if set(CATALOG) != set(CATEGORY_SLUGS):
        errors.append(f"unexpected catalog categories: {list(CATALOG)}")

    slug_owner = {}
    expected_brand_count = 0
    for category, entries in CATALOG.items():
        if len(entries) != 30:
            errors.append(f"category {category} must contain 30 merchants, got {len(entries)}")
        expected_brand_count += len(entries)
        for entry in entries:
            brand = entry["name"]
            slug = brand_slug(brand)
            owner = slug_owner.get(slug)
            if owner and owner != brand:
                errors.append(f"brand slug collision: {owner!r} and {brand!r} -> {slug}")
            slug_owner[slug] = brand

    for item in active:
        hit = resolve_brand(item.get("merchant"))
        if not hit:
            errors.append(f"active offer has unknown merchant: {item.get('merchant')!r}")
            continue
        if item.get("category") != hit["category"]:
            errors.append(f"category mismatch for {hit['name']}: {item.get('category')!r} != {hit['category']}")
        if not official_destination(item, hit):
            errors.append(f"active offer destination is outside verified merchant domain: {hit['name']}")

    for category, slug in CATEGORY_SLUGS.items():
        if not (ROOT / slug / "index.html").exists():
            errors.append(f"missing category page: {ROOT / slug / 'index.html'}")

    sitemap_text = SITEMAP_BRANDS.read_text(encoding="utf-8") if SITEMAP_BRANDS.exists() else ""
    sitemap_urls = set(re.findall(r"<loc>https://deal24h\.net/brand/([^<]+)/</loc>", sitemap_text))
    expected_urls = {brand_slug(entry["name"]) for entries in CATALOG.values() for entry in entries}
    if sitemap_urls != expected_urls:
        missing = sorted(expected_urls - sitemap_urls)
        extra = sorted(sitemap_urls - expected_urls)
        if missing:
            errors.append("catalog brand missing from sitemap-brands: " + ", ".join(missing[:20]))
        if extra:
            errors.append("non-catalog brand present in sitemap-brands: " + ", ".join(extra[:20]))

    for category, entries in CATALOG.items():
        for entry in entries:
            brand = entry["name"]
            page = ROOT / "brand" / brand_slug(brand) / "index.html"
            if not page.exists():
                errors.append(f"missing brand page: {brand}")
                continue
            text = page.read_text(encoding="utf-8")
            robots_match = re.search(
                r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']+)["\']',
                text,
                flags=re.I,
            )
            if not robots_match or robots_match.group(1).strip().lower() != "index,follow":
                errors.append(f"catalog brand is not indexable: {brand}")

    html_files = list((ROOT / "brand").glob("*/index.html")) + [
        ROOT / slug / "index.html" for slug in CATEGORY_SLUGS.values()
    ]
    for path in html_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for slug in re.findall(r'href="/brand/([^/]+)/"', text):
            if not (ROOT / "brand" / slug / "index.html").exists():
                errors.append(
                    f"broken internal brand link in {path.relative_to(ROOT)}: /brand/{slug}/"
                )

    if errors:
        print("SITE VALIDATION FAILED")
        for error in errors:
            print("-", error)
        raise SystemExit(1)

    print(
        f"SITE VALIDATION PASSED: 4 categories x 30 merchants = "
        f"{expected_brand_count} indexable brand URLs; {len(active)} active offers"
    )


if __name__ == "__main__":
    main()
