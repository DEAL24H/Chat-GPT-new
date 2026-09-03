import re
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://deal24h.net'
CATEGORIES = ('fashion','beauty','consumer','home-living','food-grocery','travel-hotels')

def main():
    today = datetime.now(timezone.utc).date().isoformat()
    urls = [BASE + '/'] + [f'{BASE}/{c}/' for c in CATEGORIES]
    p = ROOT / 'sitemap-brands.xml'
    if p.exists():
        text = p.read_text(encoding='utf-8')
        urls += re.findall(r'<loc>(https://deal24h\.net/brand/[^<]+/)</loc>', text)
    ordered = list(dict.fromkeys(urls))
    expected = 1 + len(CATEGORIES) + 534
    if len(ordered) != expected:
        raise SystemExit(f'SEO SITEMAP CLEANUP FAILED: expected {expected} URLs, got {len(ordered)}')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines += [f'<url><loc>{u}</loc><lastmod>{today}</lastmod></url>' for u in ordered]
    lines += ['</urlset>']
    (ROOT / 'sitemap.xml').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'SEO SITEMAP CLEANUP: {len(ordered)} URLs; date={today}')

if __name__ == '__main__': main()
