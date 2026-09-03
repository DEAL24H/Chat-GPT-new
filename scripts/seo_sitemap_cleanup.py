import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://deal24h.net"
CATEGORIES = ("fashion", "beauty", "gaming", "consumer")


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    urls = [BASE + "/"] + [f"{BASE}/{category}/" for category in CATEGORIES]
    brands = ROOT / "sitemap-brands.xml"
    if brands.exists():
        text = brands.read_text(encoding="utf-8")
        urls.extend(re.findall(r"<loc>(https://deal24h\\.net/brand/[^<]+/)</loc>", text))

    # Keep the main sitemap free of duplicate brand URLs while still exposing
    # the homepage and the four crawlable category hubs.
    seen = set()
    ordered = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            ordered.append(url)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines += [f"<url><loc>{url}</loc><lastmod>{today}</lastmod></url>" for url in ordered]
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"SEO SITEMAP CLEANUP: {len(ordered)} URLs in sitemap.xml; brand URLs remain only in sitemap-brands.xml")


if __name__ == "__main__":
    main()
