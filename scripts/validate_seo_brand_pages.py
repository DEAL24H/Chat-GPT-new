import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "international_brand_registry.json"
BASE = "https://deal24h.net"


def fail(msg):
    raise SystemExit(f"SEO VALIDATION FAILED: {msg}")


def main():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    categories = data["categories"]
    expected = []

    for category, entries in categories.items():
        for entry in entries:
            name = entry["name"]
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            path = ROOT / "brand" / slug / "index.html"
            if not path.exists():
                fail(f"missing brand page for {name}: {path}")
            html = path.read_text(encoding="utf-8")
            official = "https://" + entry["domain"].removeprefix("www.") + "/"
            canonical = f"{BASE}/brand/{slug}/"

            if '<meta name="robots" content="index,follow">' not in html:
                fail(f"{name}: page is not index,follow")
            if f'<link rel="canonical" href="{canonical}">' not in html:
                fail(f"{name}: canonical is not DEAL24H brand URL")
            if f'<h2 id="brand-about-title">About {name}</h2>' not in html:
                fail(f"{name}: permanent About block missing")
            if f'href="{official}"' not in html:
                fail(f"{name}: official homepage link missing or wrong")
            if f'href="{BASE}/brand/{slug}/"' in html:
                pass
            expected.append(canonical)

    sitemap = (ROOT / "sitemap-brands.xml").read_text(encoding="utf-8") if (ROOT / "sitemap-brands.xml").exists() else ""
    for url in expected:
        if f"<loc>{url}</loc>" not in sitemap:
            fail(f"brand sitemap missing {url}")

    print(f"SEO VALIDATION PASSED: {len(expected)} brand pages are indexable, canonicalized to DEAL24H, contain permanent About blocks, and link to their registered official homepage.")


if __name__ == "__main__":
    main()
