import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.catalog_utils import brand_slug

DATA = ROOT / "data" / "news.json"
BASE = "https://deal24h.net"
PROMO_RE = re.compile(r"\b(?:sale|offer|offers|deal|deals|promotion|promotions|discount|coupon|promo|clearance|special offer|save|savings|voucher|limited time|bundle|buy\s+\d+\s+get\s+\d+|buy one get one|free (?:gift|shipping|delivery|item|set)|gift with purchase|no code required|code not required|member (?:price|savings|offer))\b", re.I)
BENEFIT_RE = re.compile(r"(?:\b\d{1,3}\s*%\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?\b|\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\bbuy\s+\d+\s+get\s+\d+\b|\bbuy one get one\b|\bfree\s+(?:gift|shipping|delivery|item|set)\b|\bgift with purchase\b|\bspend\s+\$?\d+(?:[.,]\d+)?\s*(?:or more|\+)?\b|\b(?:no code required|code not required|without (?:a )?code)\b|\bmember (?:price|savings|offer)\b|\bbundle\b)", re.I)
VISIBLE_NOISE_RE = re.compile(r"(?:your cart is empty|estimated total|current price|regular price|original price|add to wishlist|add to cart|checkout|\bcart\b|sign in|log in|login|create account|privacy policy|terms(?: and conditions)?|cookie(?:s| policy)?|product advice|shipping address|billing address|search results|compare products|recently viewed|recommended for you|sort by|filter by|size guide|store locator|customer service|help center|amazon devices small business deals)", re.I)

def esc(value): return html.escape(str(value or ""), quote=True)
def slug(value): return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
def clean(value): return re.sub(r"\s+", " ", str(value or "")).strip()

def sanitize_visible(value):
    text = clean(value)
    previous = None
    while text and text != previous:
        previous = text
        text = VISIBLE_NOISE_RE.sub(" ", text)
        text = re.sub(r"\s*[|•·]+\s*", " ", text)
        text = clean(text)
    return text

def load():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("items", [])

def valid_offer(item):
    """SEO pages may only be generated from the exact canonical published set."""
    from bot.catalog_utils import is_published_verified_offer
    if not is_published_verified_offer(item): return False
    title = sanitize_visible(item.get("title")); content = sanitize_visible(item.get("content")); purchase = clean(item.get("final_purchase_url"))
    if not title or not content or not purchase: return False
    evidence = f"{title} {content}"
    if not PROMO_RE.search(evidence): return False
    if not BENEFIT_RE.search(evidence) and not clean(item.get("code")): return False
    if re.fullmatch(r"(?:\$\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*off)?", title, re.I): return False
    return True

def meaningful_title(item, merchant):
    title = sanitize_visible(item.get("title")); title = re.sub(rf"^{re.escape(merchant)}\s*[—:-]\s*", "", title, flags=re.I)
    if title and len(title) >= 8 and not re.fullmatch(r"(?:\$\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*off)?", title, re.I): return title[:140].rsplit(" ", 1)[0] if len(title) > 140 else title
    return ""

def page(title, description, canonical, body):
    copy_js = """<script>document.querySelectorAll('.copy-code').forEach(function(b){b.addEventListener('click',function(){var c=b.dataset.code||'';var done=function(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy code'},1400)};if(navigator.clipboard){navigator.clipboard.writeText(c).then(done).catch(function(){fallback(c,done)})}else{fallback(c,done)}})});function fallback(c,done){var t=document.createElement('textarea');t.value=c;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();done()}</script>"""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="index,follow"><link rel="canonical" href="{esc(canonical)}"><meta name="description" content="{esc(description)}"><title>{esc(title)}</title><link rel="stylesheet" href="/assets/style.css?v=20260903d"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL 24H</a><a href="/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Verified merchant promotion.</div></footer>{copy_js}</body></html>'''

def make_article(item):
    merchant = sanitize_visible(item.get("merchant")) or "Merchant"
    if not valid_offer(item): return None
    title = meaningful_title(item, merchant)
    if not title: return None
    code = clean(item.get("code")); purchase = clean(item.get("final_purchase_url")); promotion_url = clean(item.get("promotion_url")); discount = sanitize_visible(item.get("discount")); content = sanitize_visible(item.get("content"))
    if not content: return None
    if len(content) > 900: content = content[:897].rsplit(" ", 1)[0] + "..."
    identity = "|".join((merchant, title, code, purchase, promotion_url, discount, content)); digest = hashlib.sha1(identity.encode()).hexdigest()[:10]
    canonical = f"{BASE}/seo/{slug(merchant)}-{slug(title)[:70]}-{digest}/"; label = "Promo code" if code else "Direct deal"
    code_html = f'<div class="code"><span><small>CODE</small><strong>{esc(code)}</strong></span><button class="copy-code" type="button" data-code="{esc(code)}">Copy code</button></div>' if code else ""
    cta = f'<a class="cta" href="{esc(purchase)}" target="_blank" rel="noopener noreferrer sponsored">{"GET CODE" if code else "GET DEAL"} ↗</a>'
    source = clean(item.get("source_url")); source_html = f'<p class="source-note">Verified from the official {esc(merchant)} source.</p>'; source_link = f'<p><a href="{esc(source)}" target="_blank" rel="noopener">View the official source</a></p>' if source else ""
    category = clean(item.get("category")); category_slug = {"Fashion":"fashion","Electronics":"electronics","Beauty & Personal Care":"beauty-personal-care","Home & Living":"home-and-living"}.get(category)
    brand_link = f'<p><a href="/brand/{brand_slug(merchant)}/">More verified {esc(merchant)} offers</a></p>'
    category_link = f'<p><a href="/{category_slug}/">More {esc(category)} offers</a></p>' if category_slug else ""
    lead_discount = f"{discount} — " if discount else ""
    body = f'<section class="hero"><p class="eyebrow">{esc(label.upper())}</p><h1>{esc(merchant)} — {esc(title)}</h1><p class="lead">{esc(lead_discount)}{esc(label)} for {esc(merchant)}.</p></section><article><h2>This {esc(label.lower())}</h2><p>{esc(content)}</p>{code_html}<p>{cta}</p>{source_html}{source_link}{brand_link}{category_link}</article>'
    return canonical, page(f"{merchant} — {title} | DEAL 24H", f"{merchant} {label.lower()}: {title}. Verified official merchant promotion with the correct purchase destination.", canonical, body), label, {"canonical": canonical, "merchant": merchant, "category": category, "title": title, "label": label}

def main():
    out = ROOT / "seo"
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    urls=[]; records=[]; counts={"code":0,"direct":0}; rejected=0
    for item in load():
        result=make_article(item)
        if not result: rejected+=1; continue
        canonical, html_text, label, record=result
        path=ROOT / canonical.removeprefix(BASE + "/").rstrip("/") / "index.html"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(html_text, encoding="utf-8"); urls.append(canonical); records.append(record); counts["code" if label=="Promo code" else "direct"] += 1
    if len(urls)!=len(set(urls)): raise SystemExit("SEO OFFER ARTICLES FAILED: duplicate canonical URLs for distinct verified offers")
    class VisibleText(HTMLParser):
        def __init__(self): super().__init__(); self.parts=[]; self.skip_depth=0
        def handle_starttag(self,tag,attrs):
            if tag.lower() in {"script","style","template","noscript"}: self.skip_depth+=1
        def handle_endtag(self,tag):
            if tag.lower() in {"script","style","template","noscript"} and self.skip_depth: self.skip_depth-=1
        def handle_data(self,data):
            if not self.skip_depth: self.parts.append(data)
        def text(self): return " ".join(self.parts)
    bad_visible=[]
    for p in out.glob("*/index.html"):
        parser=VisibleText(); parser.feed(p.read_text(encoding="utf-8"))
        if VISIBLE_NOISE_RE.search(parser.text()): bad_visible.append(str(p))
    if bad_visible: raise SystemExit("SEO OFFER ARTICLES FAILED: visible UI noise remained: "+", ".join(bad_visible[:20]))
    today=datetime.now(timezone.utc).date().isoformat(); sitemap='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+"".join(f"<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in sorted(urls))+"</urlset>\n"
    (ROOT/"sitemap-seo.xml").write_text(sitemap,encoding="utf-8")
    (out/"seo-index.json").write_text(json.dumps({"schema":1,"generated_at":datetime.now(timezone.utc).isoformat(),"counts":counts,"urls":len(urls),"rejected_non_qualified":rejected,"visible_text_noise":0,"offers":sorted(records,key=lambda x:x["canonical"])},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"seo-modes.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"counts":counts,"urls":len(urls),"rejected_non_qualified":rejected,"visible_text_noise":0},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"SEO OFFER ARTICLES: code={counts['code']} direct={counts['direct']} total={len(urls)} rejected={rejected} visible_text_noise=0")

if __name__ == "__main__": main()
