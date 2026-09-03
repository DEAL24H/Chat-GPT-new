import re
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE='https://deal24h.net'
CATEGORIES=('fashion','beauty','gaming','consumer','home-living','sports-outdoor','food-grocery','travel-hotels','software-digital-services','baby-kids-family','automotive-accessories','books-education-media')
def main():
 today=datetime.now(timezone.utc).date().isoformat();urls=[BASE+'/']+[f'{BASE}/{c}/' for c in CATEGORIES];p=ROOT/'sitemap-brands.xml'
 if p.exists():urls+=re.findall(r'<loc>(https://deal24h\.net/brand/[^<]+/)</loc>',p.read_text(encoding='utf-8'))
 ordered=list(dict.fromkeys(urls)); lines=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']+[f'<url><loc>{u}</loc><lastmod>{today}</lastmod></url>' for u in ordered]+['</urlset>'];(ROOT/'sitemap.xml').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(f'SEO SITEMAP CLEANUP 999: {len(ordered)} URLs')
if __name__=='__main__':main()
