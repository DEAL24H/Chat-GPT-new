import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.catalog_utils import brand_slug
from bot.seo_offer_articles import VISIBLE_NOISE_RE, make_article

DATA = ROOT / "data" / "news.json"
SEO = ROOT / "seo"
SEO_INDEX = SEO / "seo-index.json"
SITEMAP = ROOT / "sitemap-seo.xml"
SITEMAP_MAIN = ROOT / "sitemap.xml"
BASE = "https://deal24h.net"
CATEGORY_SLUGS = {"Fashion":"fashion","Electronics":"electronics","Beauty & Personal Care":"beauty-personal-care","Home & Living":"home-and-living"}

class VisibleText(HTMLParser):
    """Collect rendered text and links while ignoring non-visible HTML blocks."""
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self.canonical=""; self.skip_depth=0
    def handle_starttag(self, tag, attrs):
        tag=tag.lower(); attrs=dict(attrs)
        if tag in {"script","style","template","noscript"}:
            self.skip_depth+=1; return
        if self.skip_depth: return
        if tag=="a" and attrs.get("href"): self.links.append(attrs["href"])
        if tag=="link" and "canonical" in attrs.get("rel","").lower().split(): self.canonical=attrs.get("href","")
    def handle_endtag(self, tag):
        tag=tag.lower()
        if tag in {"script","style","template","noscript"}:
            if self.skip_depth: self.skip_depth-=1
            return
    def handle_data(self, data):
        if not self.skip_depth: self.parts.append(data)
    def text(self): return " ".join(self.parts)

def parse_html(path):
    parser=VisibleText(); parser.feed(path.read_text(encoding="utf-8")); return parser

def main():
    meta=json.loads((SEO/"seo-modes.json").read_text(encoding="utf-8"))
    index=json.loads(SEO_INDEX.read_text(encoding="utf-8"))
    expected_total=int(meta["urls"]); expected_counts={"code":int(meta["counts"]["code"]),"direct":int(meta["counts"]["direct"])}
    records=index.get("offers",[])
    assert int(index.get("urls",-1))==expected_total
    assert len(records)==expected_total
    files=sorted(SEO.glob("*/index.html"))
    assert len(files)==expected_total,(len(files),expected_total)

    news=json.loads(DATA.read_text(encoding="utf-8"))
    expected_by_canonical={}
    for item in news:
        result=make_article(item)
        if not result: continue
        canonical,_html,label,record=result
        expected_by_canonical[canonical]={"purchase":str(item.get("final_purchase_url") or "").strip(),"label":label,"merchant":record["merchant"],"category":record["category"],"title":record["title"]}

    index_by_canonical={r.get("canonical"):r for r in records}
    if set(index_by_canonical)!=set(expected_by_canonical):
        raise SystemExit(f"SEO INDEX MISMATCH: expected={len(expected_by_canonical)} index={len(index_by_canonical)} missing={len(set(expected_by_canonical)-set(index_by_canonical))} extra={len(set(index_by_canonical)-set(expected_by_canonical))}")

    seen=set(); counts={"code":0,"direct":0}; errors=[]; page_parsers={}
    for path in files:
        parser=parse_html(path); page_parsers[str(path)]=parser
        visible=re.sub(r"\s+"," ",parser.text()).strip(); canonical=parser.canonical.strip(); slug=path.parent.relative_to(SEO).as_posix(); expected_canonical=f"{BASE}/seo/{slug}/"
        if canonical!=expected_canonical: errors.append(f"BAD_CANONICAL:{path}:{canonical}")
        if canonical in seen: errors.append(f"DUPLICATE_CANONICAL:{canonical}")
        seen.add(canonical)
        if VISIBLE_NOISE_RE.search(visible): errors.append(f"VISIBLE_NOISE:{path}")
        expected=expected_by_canonical.get(canonical); record=index_by_canonical.get(canonical)
        if not expected or not record: errors.append(f"CANONICAL_NOT_IN_VERIFIED_OFFERS:{path}:{canonical}"); continue
        is_code="PROMO CODE" in visible and "Copy code" in visible and "GET CODE" in visible; is_direct="DIRECT DEAL" in visible and "GET DEAL" in visible and "Copy code" not in visible
        if is_code: counts["code"]+=1
        elif is_direct: counts["direct"]+=1
        else: errors.append(f"BAD_OFFER_MODE:{path}")
        if expected["label"]=="Promo code" and not is_code: errors.append(f"EXPECTED_CODE_MODE:{path}")
        if expected["label"]=="Direct deal" and not is_direct: errors.append(f"EXPECTED_DIRECT_MODE:{path}")
        if not expected["purchase"] or expected["purchase"] not in parser.links: errors.append(f"CTA_NOT_EXACT_PURCHASE_URL:{path}:{expected['purchase']}")
        brand_href=f"/brand/{brand_slug(record['merchant'])}/"; category_href=f"/{CATEGORY_SLUGS.get(record['category'], '')}/"
        if brand_href not in parser.links: errors.append(f"SEO_PAGE_MISSING_BRAND_LINK:{path}:{brand_href}")
        if not category_href or category_href=="/": errors.append(f"SEO_PAGE_BAD_CATEGORY:{path}:{record['category']}")
        elif category_href not in parser.links: errors.append(f"SEO_PAGE_MISSING_CATEGORY_LINK:{path}:{category_href}")

    if counts!=expected_counts: errors.append(f"MODE_COUNTS_MISMATCH:expected={expected_counts}:actual={counts}")

    sitemap_urls=set(re.findall(r"<loc>(https://deal24h\.net/seo/[^<]+/)</loc>",SITEMAP.read_text(encoding="utf-8"))) if SITEMAP.exists() else set()
    if sitemap_urls!=seen: errors.append(f"SITEMAP_MISMATCH:missing={len(seen-sitemap_urls)}:extra={len(sitemap_urls-seen)}")
    main_sitemap_urls=set(re.findall(r"<loc>(https://deal24h\.net/[^<]+/)</loc>",SITEMAP_MAIN.read_text(encoding="utf-8"))) if SITEMAP_MAIN.exists() else set()
    if not seen.issubset(main_sitemap_urls): errors.append(f"MAIN_SITEMAP_MISSING_SEO:missing={len(seen-main_sitemap_urls)}")

    linked_from_categories=set(); linked_from_brands=set()
    for cat,cat_slug in CATEGORY_SLUGS.items():
        p=ROOT/cat_slug/"index.html"
        if not p.exists(): errors.append(f"CATEGORY_PAGE_MISSING:{cat_slug}"); continue
        parser=parse_html(p)
        for href in parser.links:
            if href.startswith(f"{BASE}/seo/"): linked_from_categories.add(href)
            elif href.startswith("/seo/"): linked_from_categories.add(BASE+href)
    # Validate each canonical brand page once. Multiple offers from one brand are
    # expected and must not create duplicate missing-page errors.
    brand_pages={}
    for r in records:
        merchant=str(r.get("merchant") or "").strip()
        if merchant:
            brand_pages.setdefault(brand_slug(merchant), merchant)
    for slug, merchant in brand_pages.items():
        p=ROOT/"brand"/slug/"index.html"
        if not p.exists(): errors.append(f"BRAND_PAGE_MISSING:{merchant}"); continue
        parser=parse_html(p)
        page_parsers[str(p)]=parser
        for href in parser.links:
            if href.startswith(f"{BASE}/seo/"): linked_from_brands.add(href)
            elif href.startswith("/seo/"): linked_from_brands.add(BASE+href)
    if linked_from_categories!=seen: errors.append(f"CATEGORY_SEO_LINK_COVERAGE:missing={len(seen-linked_from_categories)}:extra={len(linked_from_categories-seen)}")
    if not seen.issubset(linked_from_brands): errors.append(f"BRAND_SEO_LINK_COVERAGE:missing={len(seen-linked_from_brands)}")

    if errors:
        print("GENERATED SEO VALIDATION FAILED")
        for error in errors[:100]: print("-",error)
        raise SystemExit(1)
    print(f"GENERATED SEO VALIDATION PASS: code={counts['code']} direct={counts['direct']} total={len(files)} visible_text_noise=0 canonical_unique=1 exact_cta=1 sitemap_match=1 main_sitemap_match=1 category_internal_links=1 brand_internal_links=1")

if __name__=="__main__": main()
