"""Fail-fast contract for the exact 120-root + fixed country URL crawl."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED_CATEGORIES={'Fashion','Electronics','Beauty & Personal Care','Home & Living'}
def main():
 from bot.deal_discovery_core import CATS,discovery_links,MAX_PAGES,load_sources
 from bot.merchant_country_registry import locales_for
 assert set(CATS)==EXPECTED_CATEGORIES and len(CATS)==4,CATS
 sources=load_sources();assert len(sources)==120,len(sources)
 roots=[];locales=[];targets=[]
 for source in sources:
  root=source['official_homepage'];roots.append(root);targets.append((source['merchant'],'Gốc / Quốc tế',root))
  for row in locales_for(source['merchant']):
   locales.append(row['url']);targets.append((source['merchant'],row['market'],row['url']))
 assert len({s['merchant'] for s in sources})==120
 assert len(roots)==120
 assert len(locales)==319,f'fixed locale URLs={len(locales)} expected 319'
 assert len(targets)==439,f'targets={len(targets)} expected 439'
 assert MAX_PAGES==1,MAX_PAGES
 assert discovery_links(None,'example.com')==[],'dynamic link discovery is enabled'
 assert all(url.startswith(('http://','https://')) and url.strip() for _,_,url in targets)
 print('FIXED CRAWL CONTRACT PASS: 120 roots + 319 unique listed country URLs = 439 exact targets; no dynamic link crawling')
if __name__=='__main__':main()
