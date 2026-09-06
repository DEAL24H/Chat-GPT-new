import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'news.json'
BASE = 'https://deal24h.net'

def esc(v): return html.escape(str(v or ''), quote=True)
def slug(v): return re.sub(r'[^a-z0-9]+', '-', str(v or '').lower()).strip('-')
def clean(v): return re.sub(r'\s+', ' ', str(v or '')).strip()
def load():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    return data if isinstance(data, list) else data.get('items', [])
def offer_title(item, merchant):
    title = clean(item.get('title'))
    title = re.sub(rf'^{re.escape(merchant)}\s*[—-]\s*', '', title, flags=re.I)
    return title or clean(item.get('content'))[:120] or f'{merchant} official promotion'
def offer_type(item): return 'code' if clean(item.get('code')) else 'direct'
def page(title, description, canonical, body):
    copy_js = '''<script>document.querySelectorAll('.copy-code').forEach(function(b){b.addEventListener('click',function(){var c=b.dataset.code||'';var done=function(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy code'},1400)};if(navigator.clipboard){navigator.clipboard.writeText(c).then(done).catch(function(){fallback(c,done)})}else{fallback(c,done)}})});function fallback(c,done){var t=document.createElement('textarea');t.value=c;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();done()}</script>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="index,follow"><link rel="canonical" href="{esc(canonical)}"><meta name="description" content="{esc(description)}"><title>{esc(title)}</title><link rel="stylesheet" href="/assets/style.css?v=20260903d"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL 24H</a><a href="/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Verified merchant offer.</div></footer>{copy_js}</body></html>'''
def make_article(item):
    merchant = clean(item.get('merchant')) or 'Merchant'
    code = clean(item.get('code'))
    purchase = clean(item.get('final_purchase_url'))
    if not purchase: return None
    typ = offer_type(item); title = offer_title(item, merchant); discount = clean(item.get('discount'))
    content = clean(item.get('content')) or title
    if len(content) > 900: content = content[:897].rsplit(' ', 1)[0] + '...'
    digest = hashlib.sha1(f"{merchant}|{title}|{code}|{purchase}".encode()).hexdigest()[:10]
    canonical = f"{BASE}/seo/{slug(merchant)}-{slug(title)[:70]}-{digest}/"
    label = 'Promo code' if typ == 'code' else 'Direct deal'
    code_html = f'''<div class="code"><span><small>CODE</small><strong>{esc(code)}</strong></span><button class="copy-code" type="button" data-code="{esc(code)}">Copy code</button></div>''' if typ == 'code' else ''
    cta = f'<a class="cta" href="{esc(purchase)}" target="_blank" rel="noopener noreferrer sponsored">{"GET CODE" if typ == "code" else "GET DEAL"} ↗</a>'
    source = clean(item.get('source_url'))
    source_html = f'<p class="source-note">Verified from the official {esc(merchant)} source.</p>'
    source_link = f'<p><a href="{esc(source)}" target="_blank" rel="noopener">View the official source</a></p>' if source else ''
    body = f'''<section class="hero"><p class="eyebrow">{esc(label.upper())}</p><h1>{esc(merchant)} — {esc(title)}</h1><p class="lead">{esc(discount) + ' — ' if discount else ''}{esc(label)} for {esc(merchant)}.</p></section><article><h2>This {esc(label.lower())}</h2><p>{esc(content)}</p>{code_html}<p>{cta}</p>{source_html}{source_link}</article>'''
    return canonical, page(f'{merchant} — {title} | DEAL 24H', f'{merchant} {label.lower()}: {title}. Verified official merchant offer with the correct purchase destination.', canonical, body), typ
def main():
    out = ROOT / 'seo'
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    urls=[]; counts={'code':0,'direct':0}
    for item in load():
        if not isinstance(item, dict) or item.get('status') == 'expired': continue
        result=make_article(item)
        if not result: continue
        canonical, html_text, typ=result
        path=ROOT / canonical.removeprefix(BASE + '/').rstrip('/') / 'index.html'
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(html_text, encoding='utf-8')
        urls.append(canonical); counts[typ]+=1
    today=datetime.now(timezone.utc).date().isoformat()
    sitemap='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+''.join(f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n' for u in sorted(set(urls)))+'</urlset>\n'
    (ROOT/'sitemap-seo.xml').write_text(sitemap, encoding='utf-8')
    (out/'seo-modes.json').write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),'counts':counts,'urls':len(urls)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"SEO OFFER ARTICLES: code={counts['code']} direct={counts['direct']} total={len(urls)}")
if __name__ == '__main__': main()
