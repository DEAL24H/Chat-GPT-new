import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
BASE = "https://deal24h.net"

PROMO_RE = re.compile(
    r"\b(?:sale|offer|offers|deal|deals|promotion|promotions|discount|coupon|promo|"
    r"clearance|special offer|save|savings|voucher|limited time|bundle|"
    r"buy\s+\d+\s+get\s+\d+|buy one get one|free (?:gift|shipping|delivery|item|set)|"
    r"gift with purchase|no code required|code not required|member (?:price|savings|offer))\b",
    re.I,
)
BENEFIT_RE = re.compile(
    r"(?:\b\d{1,3}\s*%\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?\b|"
    r"\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\bbuy\s+\d+\s+get\s+\d+\b|"
    r"\bbuy one get one\b|\bfree\s+(?:gift|shipping|delivery|item|set)\b|"
    r"\bgift with purchase\b|\bspend\s+\$?\d+(?:[.,]\d+)?\s*(?:or more|\+)?\b|"
    r"\b(?:no code required|code not required|without (?:a )?code)\b|"
    r"\bmember (?:price|savings|offer)\b|\bbundle\b)",
    re.I,
)
BAD_TEXT_RE = re.compile(
    r"\b(?:your cart is empty|estimated total|current price|original price|"
    r"add to wishlist|add to cart|checkout|sign in|log in|login|create account|"
    r"privacy policy|terms(?: and conditions)?|cookie(?:s| policy)?|product advice|"
    r"shipping address|billing address|search results|compare products|recently viewed|"
    r"recommended for you|sort by|filter by|size guide|store locator|customer service|help center|"
    r"amazon devices small business deals)\b",
    re.I,
)

# Scraped pages frequently contain navigation/product-card/UI fragments around
# the real promotion. Remove those fragments before publishing SEO text rather
# than rejecting an otherwise verified offer.
NOISE_FRAGMENT_RE = re.compile(
    r"(?:your cart is empty|estimated total|current price|original price|add to wishlist|"
    r"add to cart|checkout|sign in|log in|login|create account|privacy policy|"
    r"terms(?: and conditions)?|cookie(?:s| policy)?|product advice|shipping address|"
    r"billing address|search results|compare products|recently viewed|recommended for you|"
    r"sort by|filter by|size guide|store locator|customer service|help center|"
    r"amazon devices small business deals)",
    re.I,
)


def esc(value):
    return html.escape(str(value or ""), quote=True)


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_content(value):
    text = clean(value)
    if not text:
        return ""
    text = NOISE_FRAGMENT_RE.sub(" ", text)
    # Remove common punctuation-only separators left after UI fragments.
    text = re.sub(r"\s*[|•·]+\s*", " ", text)
    return clean(text)


def load():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("items", [])


def valid_offer(item):
    if not isinstance(item, dict):
        return False
    if item.get("offer_qualified") is not True:
        return False
    if item.get("purchase_url_verification_status") != "live_verified":
        return False
    if item.get("status") in {"expired", "inactive"}:
        return False
    title = clean(item.get("title"))
    content = clean_content(item.get("content"))
    purchase = clean(item.get("final_purchase_url"))
    if not title or not content or not purchase:
        return False
    if BAD_TEXT_RE.search(title):
        return False
    evidence = f"{title} {content}"
    if not PROMO_RE.search(evidence):
        return False
    if not BENEFIT_RE.search(evidence) and not clean(item.get("code")):
        return False
    if re.fullmatch(r"(?:\$\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*off)?", title, re.I):
        return False
    return True


def meaningful_title(item, merchant):
    title = clean(item.get("title"))
    title = re.sub(rf"^{re.escape(merchant)}\s*[—:-]\s*", "", title, flags=re.I)
    if title and len(title) >= 8 and not re.fullmatch(r"(?:\$\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*off)?", title, re.I):
        return title[:140].rsplit(" ", 1)[0] if len(title) > 140 else title
    return ""


def page(title, description, canonical, body):
    copy_js = """<script>document.querySelectorAll('.copy-code').forEach(function(b){b.addEventListener('click',function(){var c=b.dataset.code||'';var done=function(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy code'},1400)};if(navigator.clipboard){navigator.clipboard.writeText(c).then(done).catch(function(){fallback(c,done)})}else{fallback(c,done)}})});function fallback(c,done){var t=document.createElement('textarea');t.value=c;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();done()}</script>"""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="index,follow"><link rel="canonical" href="{esc(canonical)}"><meta name="description" content="{esc(description)}"><title>{esc(title)}</title><link rel="stylesheet" href="/assets/style.css?v=20260903d"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL 24H</a><a href="/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Verified merchant promotion.</div></footer>{copy_js}</body></html>'''


def make_article(item):
    merchant = clean(item.get("merchant")) or "Merchant"
    if not valid_offer(item):
        return None
    title = meaningful_title(item, merchant)
    if not title:
        return None
    code = clean(item.get("code"))
    purchase = clean(item.get("final_purchase_url"))
    promotion_url = clean(item.get("promotion_url"))
    discount = clean(item.get("discount"))
    content = clean_content(item.get("content"))
    if len(content) > 900:
        content = content[:897].rsplit(" ", 1)[0] + "..."
    identity = "|".join((merchant, title, code, purchase, promotion_url, discount, content))
    digest = hashlib.sha1(identity.encode()).hexdigest()[:10]
    canonical = f"{BASE}/seo/{slug(merchant)}-{slug(title)[:70]}-{digest}/"
    label = "Promo code" if code else "Direct deal"
    code_html = (
        f'<div class="code"><span><small>CODE</small><strong>{esc(code)}</strong></span>'
        f'<button class="copy-code" type="button" data-code="{esc(code)}">Copy code</button></div>'
        if code else ""
    )
    cta = f'<a class="cta" href="{esc(purchase)}" target="_blank" rel="noopener noreferrer sponsored">{"GET CODE" if code else "GET DEAL"} ↗</a>'
    source = clean(item.get("source_url"))
    source_html = f'<p class="source-note">Verified from the official {esc(merchant)} source.</p>'
    source_link = f'<p><a href="{esc(source)}" target="_blank" rel="noopener">View the official source</a></p>' if source else ""
    body = (
        f'<section class="hero"><p class="eyebrow">{esc(label.upper())}</p>'
        f'<h1>{esc(merchant)} — {esc(title)}</h1>'
        f'<p class="lead">{esc(discount) + " — " if discount else ""}{esc(label)} for {esc(merchant)}.</p>'
        f'</section><article><h2>This {esc(label.lower())}</h2><p>{esc(content)}</p>'
        f'{code_html}<p>{cta}</p>{source_html}{source_link}</article>'
    )
    return canonical, page(
        f"{merchant} — {title} | DEAL 24H",
        f"{merchant} {label.lower()}: {title}. Verified official merchant promotion with the correct purchase destination.",
        canonical,
        body,
    ), label


def main():
    out = ROOT / "seo"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    urls = []
    counts = {"code": 0, "direct": 0}
    rejected = 0
    for item in load():
        result = make_article(item)
        if not result:
            rejected += 1
            continue
        canonical, html_text, label = result
        typ = "code" if label == "Promo code" else "direct"
        path = ROOT / canonical.removeprefix(BASE + "/").rstrip("/") / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html_text, encoding="utf-8")
        urls.append(canonical)
        counts[typ] += 1

    if len(urls) != len(set(urls)):
        raise SystemExit("SEO OFFER ARTICLES FAILED: duplicate canonical URLs for distinct verified offers")

    today = datetime.now(timezone.utc).date().isoformat()
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in sorted(urls))
        + "</urlset>\n"
    )
    (ROOT / "sitemap-seo.xml").write_text(sitemap, encoding="utf-8")
    (out / "seo-modes.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "counts": counts,
                "urls": len(urls),
                "rejected_non_qualified": rejected,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"SEO OFFER ARTICLES: code={counts['code']} direct={counts['direct']} total={len(urls)} rejected={rejected}")


if __name__ == "__main__": main()
