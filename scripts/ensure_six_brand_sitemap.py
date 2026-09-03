import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot.catalog_utils import brand_slug

CATALOG = ROOT / 'data' / 'brand_catalog.json'
BASE = 'https://deal24h.net'


def main():
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    categories = data.get('categories', {})
    brands = [entry for entries in categories.values() for entry in entries]
    if len(brands) != 534:
        raise SystemExit(f'BRAND SITEMAP FAILED: expected 534 brands, got {len(brands)}')
    today = datetime.now(timezone.utc).date().isoformat()
    urls = []
    seen = set()
    for brand in brands:
        url = f"{BASE}/brand/{brand_slug(brand['name'])}/"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    if len(urls) != 534:
        raise SystemExit(f'BRAND SITEMAP FAILED: expected 534 unique canonical URLs, got {len(urls)}')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines += [f'<url><loc>{u}</loc><lastmod>{today}</lastmod></url>' for u in urls]
    lines += ['</urlset>']
    (ROOT / 'sitemap-brands.xml').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'BRAND SITEMAP READY: {len(urls)} canonical indexable brands; date={today}')


if __name__ == '__main__':
    main()
