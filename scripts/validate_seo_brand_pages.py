import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
BASE = "https://deal24h.net"


def fail(msg):
    raise SystemExit(f"SEO VALIDATION FAILED: {msg}")


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower().replace("&", " and ").replace("'", "")).strip("-")


def esc(value):
    return html.escape(str(value or ""), quote=True)


def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    categories = data.get("categories", {})
    expected = []
    total = 0

    for category, entries in categories.items():
        for entry in entries:
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            total += 1
            s = slug(name)
            path = ROOT / "brand" / s / "index.html"
            if not path.exists():
                fail(f"missing generated brand page for {name}")
            html_text = path.read_text(encoding="utf-8")
            official_domain = str(entry.get("domain", "")).strip().removeprefix("www.")
            official = f"https://{official_domain}/"
            canonical = f"{BASE}/brand/{s}/"

            if '<meta name="robots" content="index,follow">' not in html_text:
                fail(f"{name}: page is not index,follow")
            if f'<link rel="canonical" href="{canonical}">' not in html_text:
                fail(f"{name}: canonical is not the DEAL24H URL")
            if f'<h2 id="brand-about-title">About {esc(name)}</h2>' not in html_text:
                fail(f"{name}: permanent About block missing")
            if official_domain and f'href="{esc(official)}"' not in html_text:
                fail(f"{name}: official homepage link does not match catalog domain")
            expected.append(canonical)

    if set(categories) != {"Fashion", "Electronics", "Beauty", "Home & Living"}:
        fail(f"legacy or unexpected categories remain: {sorted(categories)}")
    if total != 120 or any(len(entries) != 30 for entries in categories.values()):
        fail(f"catalog must contain exactly 30 brands in each of 4 categories; total={total}")

    sitemap_path = ROOT / "sitemap-brands.xml"
    if not sitemap_path.exists():
        fail("sitemap-brands.xml is missing")
    sitemap = sitemap_path.read_text(encoding="utf-8")
    missing = [u for u in expected if f"<loc>{u}</loc>" not in sitemap]
    if missing:
        fail(f"brand sitemap missing {len(missing)} generated brand URLs; first={missing[0]}")

    print(f"SEO VALIDATION PASSED: {total} brand pages across 4 current categories are indexable, canonicalized to DEAL24H, contain permanent About blocks, and link to their registered official homepage.")


if __name__ == "__main__":
    main()
