import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from catalog_utils import load_catalog
from news_bot import BAD_CODES, EXPLICIT_CODE_PATTERNS, clean, parse_expiry
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'news.json'
MAX_BRANDS=999
BATCH_SIZE=250
WORKERS=12
TIMEOUT=15
MAX_PAGES_PER_BRAND=3
MAX_BLOCKS=5
PROMO_RE=re.compile(r'\b(?:sale|deal|deals|offer|offers|promotion|promotions|coupon|coupons|discount|save|savings|clearance|voucher)\b',re.I)
DISCOUNT_RE=re.compile(r'(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%\s?(?:off|discount)?|save\s+\$?\d+(?:\.\d+)?)',re.I)
LINK_RE=re.compile(r'\b(?:shop|shop now|buy|products?|collections?|sale|deals?|offers?|coupons?|discount|eligible)\b',re.I)
def load_items():
    try:
        v=json.loads(OUT.read_text(encoding='utf-8')); return v if isinstance(v,list) else []
    except Exception:return []
def host_for(url): return (urlparse(url).hostname or '').lower().removeprefix('www.')
def official_url(domain):
    d=str(domain or '').strip().lower().removeprefix('www.'); return 'https://'+d+'/' if d else ''
def fetch(url):
    r=requests.get(url,headers={'User-Agent':'Deal24H/4.0 (+official-source-batch-collector)'},timeout=TIMEOUT,allow_redirects=True); r.raise_for_status(); return r.url,r.text
def same_domain(url,domain):
    h=host_for(url); return h==domain or h.endswith('.'+domain)
def candidate_links(page_url,html,domain):
    soup=BeautifulSoup(html,'html.parser'); out=[]; seen=set()
    for a in soup.find_all('a',href=True):
        href=urljoin(page_url,a.get('href','').strip())
        if not href.startswith('https://') or not same_domain(href,domain): continue
        text=clean(a.get_text(' ',strip=True)); hay=f'{text} {href}'
        if not LINK_RE.search(hay): continue
        path=(urlparse(href).path+' '+urlparse(href).query).lower(); score=0
        if re.search(r'promo|coupon|offer|deal|sale|discount|clearance',path,re.I): score+=20
        if re.search(r'shop|product|collection|category|sale|deal|offer',path,re.I): score+=10
        if LINK_RE.search(text): score+=8
        if re.search(r'terms|privacy|legal|help|faq|support',path,re.I): score-=20
        if href.rstrip('/')==page_url.rstrip('/'): score-=50
        if score>0 and href not in seen: seen.add(href); out.append((score,href))
    out.sort(key=lambda x:(-x[0],len(x[1]))); return [u for _,u in out[:MAX_PAGES_PER_BRAND-1]]
def blocks(html):
    soup=BeautifulSoup(html,'html.parser')
    for n in soup(['script','style','noscript','svg']): n.decompose()
    out=[]; seen=set()
    for n in soup.find_all(['article','section','li','p','div']):
        text=clean(n.get_text(' ',strip=True)); key=re.sub(r'\W+',' ',text.lower()).strip()
        if not (35<=len(text)<=650) or key in seen or not PROMO_RE.search(text): continue
        if not (DISCOUNT_RE.search(text) or re.search(r'\b(?:promotion|promotions|special offer|limited time|clearance|coupon|voucher)\b',text,re.I)): continue
        seen.add(key); out.append(text[:600])
        if len(out)>=MAX_BLOCKS: break
    return out
def codes(text):
    found=[]
    for p in EXPLICIT_CODE_PATTERNS:
        for m in p.finditer(text):
            c=m.group(1).upper()
            if c not in BAD_CODES and c not in found: found.append(c)
    return found[:5]
def make_record(brand,domain,category,source_url,destination,content,code=''):
    m=DISCOUNT_RE.search(content); discount=m.group(0) if m else ''; now=datetime.now(timezone.utc).isoformat()
    return {'id':hashlib.sha256(f'{domain}|{brand}|{code}|{content}'.encode()).hexdigest()[:16],'title':f"{brand} — {discount or ('Coupon code '+code if code else 'Official promotion')}",'content':content,'code':code,'discount':discount,'merchant':brand,'category':category,'country':'International','url':destination,'source_url':source_url,'promotion_url':destination,'source_label':f'{brand} Official Promotions','source_domain':domain,'official_source':True,'code_context':bool(code),'detected_at':now,'last_checked':now,'expires_at':parse_expiry(content) or '','status':'active','verified':False,'verification_method':'official_merchant_page_scalable','images':[],'image':'','summary_type':'official_merchant_promotion_discovery','expanded_source_collector':True,'scalable_collector':True}
def scan(entry):
    brand=str(entry.get('name','')).strip(); domain=str(entry.get('domain','')).strip().lower().removeprefix('www.'); category=str(entry.get('category','')).strip(); root=official_url(domain)
    if not brand or not domain: return brand,[],'invalid_catalog_entry'
    try:
        first_url,first_html=fetch(root); pages=[(first_url,first_html)]
        for c in candidate_links(first_url,first_html,domain):
            try: pages.append(fetch(c))
            except Exception: pass
        records=[]
        for page_url,html in pages:
            text=clean(html); bs=blocks(html); found=codes(text)
            for code in found:
                context=next((b for b in bs if code.lower() in b.lower()),f'Official promotion code {code} published on the merchant website.')
                dest=page_url if re.search(r'shop|product|collection|sale|deal|offer|promo|coupon',urlparse(page_url).path,re.I) else next((u for u in candidate_links(page_url,html,domain) if re.search(r'shop|product|collection|sale|deal|offer',urlparse(u).path,re.I)),'')
                if dest: records.append(make_record(brand,domain,category,page_url,dest,context,code))
            for t in bs:
                if found and any(c.lower() in t.lower() for c in found): continue
                dest=page_url if re.search(r'shop|product|collection|sale|deal|offer|promo|coupon',urlparse(page_url).path,re.I) else ''
                if dest: records.append(make_record(brand,domain,category,page_url,dest,t))
        u={}
        for r in records: u[(r['merchant'].lower(),r['code'].upper(),re.sub(r'\W+',' ',r['content'].lower()).strip())]=r
        return brand,list(u.values())[:MAX_BLOCKS],'ok'
    except Exception as e:return brand,[],f'error:{type(e).__name__}'
def batch_index():
    f=os.getenv('DEAL_BATCH_INDEX','').strip()
    if f.isdigit() and 0<=int(f)<4:return int(f)
    now=datetime.now(timezone.utc); slots={(23,0):0,(23,30):1,(0,0):2,(0,30):3,(7,0):0,(7,30):1,(8,0):2,(8,30):3,(15,0):0,(15,30):1,(16,0):2,(16,30):3}; return slots.get((now.hour,now.minute),0)
def main():
    catalog=load_catalog(); entries=[]
    for cat,vals in catalog.items():
        for v in vals if isinstance(vals,list) else []:
            x=dict(v); x['category']=cat; entries.append(x)
    entries=[x for x in entries[:MAX_BRANDS] if x.get('enabled',True) and not x.get('placeholder') and str(x.get('domain','')).strip()]
    b=batch_index(); batch=entries[b*BATCH_SIZE:(b+1)*BATCH_SIZE]; names={str(x.get('name','')).strip().lower() for x in batch}; existing=load_items()
    retained=[x for x in existing if not (x.get('scalable_collector') and str(x.get('merchant','')).strip().lower() in names)]
    ok=fail=added=0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures={pool.submit(scan,e):e for e in batch}
        for f in as_completed(futures):
            e=futures[f]; brand,records,status=f.result(); key=brand.lower()
            if status=='ok': ok+=1; retained.extend(records); added+=len(records)
            else:
                fail+=1; retained.extend(x for x in existing if x.get('scalable_collector') and str(x.get('merchant','')).strip().lower()==key); print(f'SCALABLE SOURCE {status}: {brand}')
    dedup={}
    for x in retained:
        k=(str(x.get('merchant','')).strip().lower(),str(x.get('code','')).strip().upper(),re.sub(r'\s+',' ',str(x.get('content','')).strip().lower()))
        if k[0]: dedup[k]=x
    out=list(dedup.values())[-6000:]; OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'SCALABLE BRAND BATCH: cycle=3/day, batch={b+1}/4, batch_size={len(batch)}, capacity={MAX_BRANDS}, catalog=999, enabled_scannable={len(entries)}, success={ok}, failed={fail}, records_added={added}, total_records={len(out)}')
if __name__=='__main__': main()
