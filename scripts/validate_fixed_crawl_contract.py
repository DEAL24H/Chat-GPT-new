"""Fail-fast contract for the exact 120-root + fixed country URL crawl."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
EXPECTED_CATEGORIES={'Fashion','Electronics','Beauty & Personal Care','Home & Living'}

def main():
    from bot.deal_discovery_core import CATS,discovery_links,MAX_PAGES,load_sources
    from bot.merchant_country_registry import locales_for
    assert set(CATS)==EXPECTED_CATEGORIES and len(CATS)==4,CATS
    sources=load_sources(); assert len(sources)==120,len(sources)
    source_brands={s['merchant'].strip().casefold() for s in sources}
    assert len(source_brands)==120
    roots=[];locales=[];targets=[]
    for source in sources:
        root=source['official_homepage']; roots.append(root); targets.append((source['merchant'],'Gốc / Quốc tế',root))
        for row in locales_for(source['merchant']):
            locales.append(row['url']); targets.append((source['merchant'],row['market'],row['url']))
    assert len(roots)==120 and len(set(roots))==120
    assert len(locales)==319 and len(set(locales))==319,f'fixed locale URLs={len(locales)} expected 319'
    assert len(targets)==439 and len(set(url for _,_,url in targets))==439
    registry_brands={str(k).strip().casefold() for k in __import__('bot.merchant_country_registry',fromlist=['REGISTRY']).REGISTRY}
    assert registry_brands==source_brands,f'brand registry mismatch: registry={len(registry_brands)} source={len(source_brands)}'
    assert MAX_PAGES==1,MAX_PAGES
    assert discovery_links(None,'example.com')==[],'dynamic link discovery is enabled'
    assert all(url.startswith(('http://','https://')) and url.strip() for _,_,url in targets)
    print('FIXED CRAWL CONTRACT PASS: source/registry brands=120; 120 roots + 319 unique listed country URLs = 439 exact targets; no dynamic link crawling')
if __name__=='__main__':main()
