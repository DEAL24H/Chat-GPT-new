"""Canonical offer parser for assistant-verified first-party merchant pages.

This module intentionally supports BOTH:
- coupon/code promotions; and
- automatic/direct promotions that require no code.

It never changes source authority: callers must provide an assistant-verified
first-party source, and downstream exact-purchase verification remains mandatory.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

CODE_RE = r"[A-Z0-9][A-Z0-9_-]{3,24}"
EXPLICIT_CODE_PATTERNS = [
    re.compile(r"\b(?:use|enter)\s+(?:the\s+)?(?:promo(?:tion)?\s+)?code\s*(?:is\s*)?[:=]\s*[\"'“”]?((?:%s))[\"'“”]?\b" % CODE_RE, re.I),
    re.compile(r"\b(?:use|enter)\s+(?:the\s+)?(?:promo(?:tion)?\s+)?code\s+[\"'“”]((?:%s))[\"'“”]" % CODE_RE, re.I),
    re.compile(r"\b(?:promo(?:tion)?\s+code|coupon\s+code|voucher\s+code|code)\s*[:=]\s*[\"'“”]?((?:%s))[\"'“”]?\b" % CODE_RE, re.I),
]
DISCOUNT_RE = re.compile(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}(?:\.\d+)?\s?%\s?(?:off)?|\d{1,3}\s?%\s?off)", re.I)
PROMO_RE = re.compile(
    r"\b(?:sale|offer|offers|deal|deals|promotion|promotions|discount|clearance|special(?: offer|s)?|save|\d{1,3}%\s*off|"
    r"buy\s+\d+\s+get\s+\d+|buy one get one|free\s+(?:gift|shipping|delivery|item|set)|gift with purchase|"
    r"spend\s+\$?\d+|\$?\d+\s*(?:minimum|or more|\+)|automatic(?:ally)?\s+discount|no code required|"
    r"without\s+(?:a\s+)?code|code\s+not\s+required|bundle|member price|member savings)\b",
    re.I,
)
BAD_CODES = {
    "COPY","CODE","COUPON","COUPONS","TODAY","DEAL","DEALS","SALE","NEW","SHOP","HTTPS","WWW",
    "CLICK","VERIFY","AUTHORITY","EDITORS","EDITOR","HAND-TESTED","TESTED","POPULAR","LATEST",
    "ACTIVE","EXCLUSIVE","PROMO","PROMOS","OFFER","OFFERS","WITH","ENTER","THIS","YOUR","FROM",
    "ONLY","APPLY","HELP","PAGE","NEXT","SIGN","JOIN","REQUIRED","INTO",
}
MONTHS = {
    "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,
    "may":5,"jun":6,"june":6,"jul":7,"july":7,"aug":8,"august":8,"sep":9,
    "sept":9,"september":9,"oct":10,"october":10,"nov":11,"november":11,
    "dec":12,"december":12,
}


def clean(text):
    return re.sub(r"\s+", " ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def official_domain(url):
    return urlparse(str(url or "")).netloc.lower().removeprefix("www.")


def is_official_source(source):
    domain = official_domain(source.get("url", ""))
    allowed = str(source.get("domain", "")).lower().removeprefix("www.")
    return bool(domain and allowed and (domain == allowed or domain.endswith("." + allowed)))


def parse_date(raw):
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw.strip(), flags=re.I)
    raw = re.sub(r"\s+", " ", raw).replace("/", "-")
    for fmt in ("%m-%d-%Y","%m-%d-%y","%d-%m-%Y","%d-%m-%y","%b %d, %Y","%B %d, %Y","%b %d %Y","%B %d %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", raw)
    if match and MONTHS.get(match.group(2).lower()):
        return datetime(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)), tzinfo=timezone.utc).isoformat()
    return ""


def parse_expiry(text):
    text = clean(text)
    patterns = [
        r"\b(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?|ends on)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"\b(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?|ends on)\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)",
        r"\b(?:through|until)\s+([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4}))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed
    return ""


def extract_codes(text):
    found = []
    for pattern in EXPLICIT_CODE_PATTERNS:
        for match in pattern.findall(text):
            code = match.upper()
            if code not in BAD_CODES and code not in found:
                found.append(code)
    return found[:5]


def _candidate_blocks(soup):
    blocks = []
    seen = set()
    for tag in soup.find_all(["article", "li", "section", "div"]):
        text = clean(tag.get_text(" ", strip=True))
        if not 25 <= len(text) <= 1200:
            continue
        if not PROMO_RE.search(text) and not extract_codes(text):
            continue
        # Avoid publishing huge parent containers that merely repeat child offers.
        key = re.sub(r"\W+", " ", text.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        blocks.append((tag, text))
    return blocks


def _structured_offers(soup):
    results = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            payload = json.loads(script.string or script.get_text())
        except Exception:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                if "offers" in obj:
                    stack.extend(obj["offers"] if isinstance(obj["offers"], list) else [obj["offers"]])
                if any(k in obj for k in ("price", "priceSpecification", "discount")):
                    text = clean(json.dumps(obj, ensure_ascii=False))
                    if PROMO_RE.search(text) or re.search(r"discount|sale|priceSpecification", text, re.I):
                        results.append(text[:1200])
                for value in obj.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(obj, list):
                stack.extend(obj)
    return results


def _is_valid_direct_offer(text, discount, codes):
    if codes:
        return True
    # A direct promotion needs affirmative promotional evidence. A bare price is not enough.
    if not PROMO_RE.search(text):
        return False
    return bool(discount or re.search(
        r"\b(?:free\s+(?:gift|shipping|delivery|item|set)|gift with purchase|buy\s+\d+\s+get\s+\d+|"
        r"spend\s+\$?\d+|no code required|without\s+(?:a\s+)?code|code\s+not\s+required|bundle|member savings)\b",
        text,
        re.I,
    ))


def extract_deals(html, source):
    """Extract both coded and automatic/direct promotions from one verified page.

    The exact purchase destination is deliberately NOT inferred here. The canonical
    pipeline performs a separate same-merchant exact-destination verification step.
    """
    if not is_official_source(source):
        return []
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = _candidate_blocks(soup)
    structured = _structured_offers(soup)
    deals, seen = [], set()
    merchant = source["merchant"]
    category = source["category"]

    for tag, block in candidates:
        codes = extract_codes(block)
        discount_match = DISCOUNT_RE.search(block)
        discount = discount_match.group(0) if discount_match else ""
        if not _is_valid_direct_offer(block, discount, codes):
            continue
        signature = re.sub(r"\W+", " ", block.lower()).strip()[:500]
        if signature in seen:
            continue
        seen.add(signature)
        code = codes[0] if codes else ""
        label = discount or ("Official promotion" if not code else "Official promo code")
        deal = {
            "id": hashlib.sha256((source["name"] + "|" + merchant + "|" + signature).encode()).hexdigest()[:16],
            "title": f"{merchant} — {label}",
            "content": block[:700],
            "code": code,
            "discount": discount,
            "merchant": merchant,
            "category": category,
            "country": "International",
            "url": source["url"],
            "source_url": source["url"],
            "source_label": source["name"],
            "source_domain": source["domain"],
            "official_source": True,
            "code_context": bool(code),
            "promotion_type": "coupon_code" if code else "automatic_direct_promotion",
            "detected_at": now(),
            "last_checked": now(),
            "expires_at": parse_expiry(block),
            "status": "active",
            "verified": False,
            "verification_method": "official_merchant_page",
            "images": [],
            "image": "",
            "summary_type": "official_merchant_promotion_discovery",
        }
        deals.append(deal)

    # Structured data is a fallback only; it can discover offers that are not exposed
    # as normal HTML blocks. It still must contain affirmative promotion evidence.
    for text in structured:
        codes = extract_codes(text)
        discount_match = DISCOUNT_RE.search(text)
        discount = discount_match.group(0) if discount_match else ""
        if not _is_valid_direct_offer(text, discount, codes):
            continue
        signature = re.sub(r"\W+", " ", text.lower()).strip()[:500]
        if signature in seen:
            continue
        seen.add(signature)
        code = codes[0] if codes else ""
        label = discount or ("Official promotion" if not code else "Official promo code")
        deals.append({
            "id": hashlib.sha256((source["name"] + "|" + merchant + "|" + signature).encode()).hexdigest()[:16],
            "title": f"{merchant} — {label}",
            "content": text[:700],
            "code": code,
            "discount": discount,
            "merchant": merchant,
            "category": category,
            "country": "International",
            "url": source["url"],
            "source_url": source["url"],
            "source_label": source["name"],
            "source_domain": source["domain"],
            "official_source": True,
            "code_context": bool(code),
            "promotion_type": "coupon_code" if code else "automatic_direct_promotion",
            "detected_at": now(),
            "last_checked": now(),
            "expires_at": parse_expiry(text),
            "status": "active",
            "verified": False,
            "verification_method": "official_merchant_page_structured_data",
            "images": [],
            "image": "",
            "summary_type": "official_merchant_promotion_discovery",
        })
    return deals


if __name__ == "__main__":
    raise SystemExit("news_bot.py is a library module; run bot/assistant_verified_news_runner.py for the canonical pipeline")
