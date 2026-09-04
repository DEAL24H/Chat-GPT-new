#!/usr/bin/env python3
import json, sys
from pathlib import Path

CATALOG = Path('data/brand_catalog.json')
EXPECTED = {'Fashion':89,'Beauty':89,'Consumer':89,'Home & Living':89,'Food & Grocery':89,'Travel & Hotels':89}
FORBIDDEN = {'w3.org','google.com','google.co.uk','bing.com','duckduckgo.com','wikipedia.org','facebook.com','instagram.com','youtube.com','tiktok.com','x.com','twitter.com','reddit.com','pinterest.com','linkedin.com','yelp.com','trustpilot.com','rakuten.com','retailmenot.com','groupon.com','slickdeals.net','coupons.com'}
OVERRIDES = {'ASOS':'asos.com','Fendi':'fendi.com','Gucci':'gucci.com','H&M':'hm.com','Lululemon':'lululemon.com','Prada':'prada.com','UNIQLO':'uniqlo.com'}

def host(v):
    v=(v or '').lower().strip().replace('https://','').replace('http://','').split('/')[0].split(':')[0]
    return v[4:] if v.startswith('www.') else v

def main():
    data=json.loads(CATALOG.read_text(encoding='utf-8'))
    cats=data.get('categories',{})
    errors=[]; changed=[]; seen=set(); total=0
    if set(cats) != set(EXPECTED): errors.append(f'categories mismatch: {sorted(cats)}')
    for category, expected in EXPECTED.items():
        entries=cats.get(category,[])
        if len(entries)!=expected: errors.append(f'{category}: expected {expected}, got {len(entries)}')
        for e in entries:
            total+=1; name=str(e.get('name','')).strip(); d=host(e.get('domain'))
            if name.casefold() in seen: errors.append(f'duplicate brand: {name}')
            seen.add(name.casefold())
            if not name: errors.append(f'{category}: blank brand name')
            if name in OVERRIDES and d != OVERRIDES[name]:
                e['domain']=OVERRIDES[name]; e['catalog_status']='verified_first_party'; changed.append(f'{name}: {d} -> {OVERRIDES[name]}')
            d=host(e.get('domain'))
            if d in FORBIDDEN: errors.append(f'{name}: forbidden/non-brand domain {d}')
            if not d: errors.append(f'{name}: missing domain')
            if e.get('catalog_status')=='verified_first_party_search': errors.append(f'{name}: untrusted search-derived verification')
            e['enabled']=True; e.pop('placeholder',None)
    if total!=534: errors.append(f'total expected 534, got {total}')
    # This is an integrity gate, not a discovery engine: uncertain sources fail closed.
    CATALOG.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if errors:
        print('STRICT CATALOG AUDIT: FAILED')
        for x in errors: print('ERROR:',x)
        for x in changed: print('CHANGE:',x)
        sys.exit(1)
    print('STRICT CATALOG AUDIT: PASS')
    print('Total brands:',total)
    print('Categories:', ', '.join(f'{k}={len(cats[k])}' for k in EXPECTED))
    print('Corrections:',len(changed))

if __name__=='__main__': main()
