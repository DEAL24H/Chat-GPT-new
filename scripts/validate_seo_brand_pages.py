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


def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    categories = data.get("categories", {})
    expected = []

    for category, entries in categories.items():
        for entry in entries:
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            s = slug(name)
            path = ROOT / "brand" / s / "index.html"
            if not path.exists():
                fail(f"missing generated brand page for {name}")
            html = path.read_text(encoding="utf-8")
            official_domain = str(entry.get("domain", "")).strip().removeprefix("www.")
            official = f"https://{official_domain}/"
            canonical = f"{BASE}/brand/{s}/"

            if '<meta name="robots" content="index,follow">' not in html:
                fail(f"{name}: page is not index,follow")
            if f'<link rel="canonical" href="{canonical}">' not in html:
                fail(f"{name}: canonical is not the DEAL24H URL")
            if f'<h2 id="brand-about-title">About {name}</h2>' not in html:
                fail(f"{name}: permanent About block missing")
            if official_domain and f'href="{official}"' not in html:
                fail(f"{name}: official homepage link does not match catalog domain")
            expected.append(canonical)

    sitemap_path = ROOT / "sitemap-brands.xml"
    if not sitemap_path.exists():
        fail("sitemap-brands.xml is missing")
    sitemap = sitemap_path.read_text(encoding="utf-8")
    missing = [u for u in expected if f"<loc>{u}</loc>" not in sitemap]
    if missing:
        fail(f"brand sitemap missing {len(missing)} generated brand URLs; first={missing[0]}")

    print(f"SEO VALIDATION PASSED: {len(expected)} catalog brand pages are indexable, canonicalized to DEAL24H, contain permanent About blocks, and link to their registered official homepage.")


if __name__ == "__main__":
    main()
