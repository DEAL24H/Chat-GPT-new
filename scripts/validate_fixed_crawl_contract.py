"""Fail-fast contract for the exact 120-root + fixed country URL crawl."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
EXPECTED_CATEGORIES={'Fashion','Electronics','Beauty & Personal Care','Home & Living'}
EXPECTED_BRANDS=120
EXPECTED_ROOTS=120
EXPECTED_LOCALES=320
EXPECTED_TARGETS=440

def main():
    from bot.deal_discovery_core import CATS,discovery_links,MAX_PAGES,load_sources
    from bot.merchant_country_registry import locales_for,REGISTRY
    assert set(CATS)==EXPECTED_CATEGORIES and len(CATS)==4,CATS
    sources=load_sources();assert len(sources)==EXPECTED_BRANDS,len(sources)
    source_brands={s['merchant'].strip().casefold() for s in sources};assert len(source_brands)==EXPECTED_BRANDS
    roots=[];locales=[];targets=[]
    for source in sources:
        root=source['official_homepage'];roots.append(root);targets.append((source['merchant'],'Gốc / Quốc tế',root))
        for row in locales_for(source['merchant']):
            locales.append(row['url']);targets.append((source['merchant'],row['market'],row['url']))
    assert len(roots)==EXPECTED_ROOTS and len(set(roots))==EXPECTED_ROOTS
    assert len(locales)==EXPECTED_LOCALES and len(set(locales))==EXPECTED_LOCALES,f'fixed locale URLs={len(locales)} expected {EXPECTED_LOCALES}'
    assert len(targets)==EXPECTED_TARGETS and len(set(url for _,_,url in targets))==EXPECTED_TARGETS
    registry_brands={str(k).strip().casefold() for k in REGISTRY};assert registry_brands==source_brands,f'brand registry mismatch: registry={len(registry_brands)} source={len(source_brands)}'
    assert MAX_PAGES==1,MAX_PAGES
    assert discovery_links(None,'example.com')==[],'dynamic link discovery is enabled'
    assert all(url.startswith(('http://','https://')) and url.strip() for _,_,url in targets)
    print(f'FIXED CRAWL CONTRACT PASS: source/registry brands={EXPECTED_BRANDS}; {EXPECTED_ROOTS} roots + {EXPECTED_LOCALES} unique listed country/market URLs = {EXPECTED_TARGETS} exact targets; no dynamic link crawling')

if __name__=='__main__':main()
