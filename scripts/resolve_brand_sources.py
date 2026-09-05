import json,re,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from urllib.parse import quote,urlparse
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]; CATALOG=ROOT/'data'/'brand_catalog.json'; OUT=ROOT/'data'/'brand_sources.json'
UA={'User-Agent':'Deal24H/4.0 (canonical brand source verifier; https://deal24h.net/)'}; TIMEOUT=15; WORKERS=12
BAD_HOSTS={'facebook.com','instagram.com','youtube.com','linkedin.com','twitter.com','x.com','tiktok.com','wikipedia.org','amazon.com','amazon.co.uk','amazon.co.jp','walmart.com','ebay.com','shopee.vn','lazada.vn'}

def host(u):
    try:return (urlparse(u).hostname or '').lower().removeprefix('www.')
    except Exception:return ''
def valid_url(u):
    h=host(u); return bool(h) and h not in BAD_HOSTS and not any(h.endswith('.'+x) for x in BAD_HOSTS)
def search_wikipedia(name):
    q=quote(name)
    api=f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=5'
    r=requests.get(api,headers=UA,timeout=TIMEOUT); r.raise_for_status()
    hits=r.json().get('query',{}).get('search',[])
    return [h.get('title','') for h in hits]
def official_from_page(title):
    if not title:return None
    api=f'https://en.wikipedia.org/w/api.php?action=parse&page={quote(title)}&prop=text|externallinks&format=json'
    r=requests.get(api,headers=UA,timeout=TIMEOUT); r.raise_for_status(); d=r.json().get('parse',{})
    links=d.get('externallinks',[]) or []
    for u in links:
        if valid_url(u) and host(u) not in {'wikimedia.org'}: return u
    html=d.get('text',{}).get('*','')
    soup=BeautifulSoup(html,'html.parser')
    for a in soup.find_all('a',href=True):
        txt=' '.join(a.get_text(' ',strip=True).lower().split())
        u=a.get('href','').strip()
        if ('official website' in txt or txt=='website') and valid_url(u): return u
    return None
def verify(u,name):
    if not valid_url(u):return None
    try:
        r=requests.get(u,headers=UA,timeout=TIMEOUT,allow_redirects=True)
        r.raise_for_status(); h=host(r.url)
        if not valid_url(r.url):return None
        soup=BeautifulSoup(r.text,'html.parser'); title=(soup.title.get_text(' ',strip=True) if soup.title else '')
        hay=re.sub(r'[^a-z0-9]+',' ',f'{name} {title}'.lower()).strip()
        toks=[x for x in re.findall(r'[a-z0-9]+',name.lower()) if len(x)>=4]
        if toks and not any(t in hay for t in toks): return None
        return r.url
    except Exception:return None
def one(item):
    name=item['name']; titles=[]
    try: titles=search_wikipedia(name)
    except Exception:return None
    for title in titles:
        try:
            u=official_from_page(title)
            v=verify(u,name) if u else None
            if v:return {'brand_key':item['brand_key'],'name':name,'category':item['category'],'country':item.get('country'),'domain':host(v),'url':v,'status':'verified','verification_method':'wikipedia_official_link_plus_live_homepage'}
        except Exception: pass
    return None
def main():
    d=json.loads(CATALOG.read_text(encoding='utf-8')); rows=[]
    for cat,items in d['categories'].items():
        for x in items:
            if isinstance(x,dict): rows.append(dict(x,category=cat))
            else: rows.append({'name':x,'brand_key':f'{cat}::{x.lower()}','category':cat})
    out=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        fs={ex.submit(one,x):x for x in rows}
        for i,f in enumerate(as_completed(fs),1):
            v=f.result()
            if v: out.append(v)
            if i%25==0: print(f'SOURCE RESOLUTION: {i}/{len(rows)} verified={len(out)}',flush=True)
    out.sort(key=lambda x:(x['category'],x['name'].casefold()))
    status='verified' if len(out)==len(rows) else 'incomplete'
    OUT.write_text(json.dumps({'schema':1,'status':status,'source_count':len(out),'expected_count':len(rows),'sources':out},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'SOURCE RESOLUTION RESULT: {len(out)}/{len(rows)} status={status}')
    if len(out)!=len(rows): raise SystemExit(2)
if __name__=='__main__': main()
