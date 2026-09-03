import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from catalog_utils import load_catalog
from news_bot import BAD_CODES, EXPLICIT_CODE_PATTERNS, clean, parse_expiry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
MAX_BRANDS = 1000
WORKERS = 12
TIMEOUT = 15
MAX_PAGES_PER_BRAND = 3
MAX_BLOCKS = 5
PROMO_RE = re.compile(r"\b(?:sale|deal|deals|offer|offers|promotion|promotions|coupon|coupons|discount|save|savings|clearance|voucher)\b", re.I)
DISCOUNT_RE = re.compile(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%\s?(?:off|discount)?|save\s+\$?\d+(?:\.\d+)?)", re.I)
LINK_RE = re.compile(r"\b(?:shop|shop now|buy|products?|collections?|sale|deals?|offers?|coupons?|discount|eligible)\b", re.I)
CATEGORY_MAP = {"Fashion": "Thời trang", "Beauty": "Mỹ phẩm", "Gaming": "Game", "Consumer": "Hàng tiêu dùng"}


def load_items():
    try:
        value = json.loads(OUT.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def host_for(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def official_url(domain):
    domain = str(domain or "").strip().lower().removeprefix("www.")
    if not domain:
        return ""
    return "https://" + domain + "/"


def fetch(url):
    response = requests.get(url, headers={"User-Agent": "Deal24H/3.0 (+scalable official-source collector)"}, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response.url, response.text


def same_domain(url, domain):
    host = host_for(url)
    return host == domain or host.endswith("." + domain)


def candidate_links(page_url, html, domain):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor.get("href", "").strip())
        if not href.startswith("https://") or not same_domain(href, domain):
            continue
        text = clean(anchor.get_text(" ", strip=True))
        hay = f"{text} {href}"
        if not LINK_RE.search(hay):
            continue
        parsed = urlparse(href)
        path = (parsed.path + " " + parsed.query).lower()
        score = 0
        if re.search(r"promo|coupon|offer|deal|sale|discount|clearance", path, re.I):
            score += 20
        if re.search(r"shop|product|collection|category|sale|deal|offer", path, re.I):
            score += 10
        if LINK_RE.search(text):
            score += 8
        if re.search(r"terms|privacy|legal|help|faq|support", path, re.I):
            score -= 20
        if href.rstrip("/") == page_url.rstrip("/"):
            score -= 50
        if score > 0 and href not in seen:
            seen.add(href)
            candidates.append((score, href))
    candidates.sort(key=lambda x: (-x[0], len(x[1])))
    return [url for _, url in candidates[: MAX_PAGES_PER_BRAND - 1]]


def blocks(html):
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    out, seen = [], set()
    for node in soup.find_all(["article", "section", "li", "p", "div"]):
        text = clean(node.get_text(" ", strip=True))
        key = re.sub(r"\W+", " ", text.lower()).strip()
        if not (35 <= len(text) <= 650) or key in seen:
            continue
        if not PROMO_RE.search(text):
            continue
        if not (DISCOUNT_RE.search(text) or re.search(r"\b(?:promotion|promotions|special offer|limited time|clearance|coupon|voucher)\b", text, re.I)):
            continue
        seen.add(key)
        out.append(text[:600])
        if len(out) >= MAX_BLOCKS:
            break
    return out


def codes(text):
    found = []
    for pattern in EXPLICIT_CODE_PATTERNS:
        for match in pattern.finditer(text):
            code = match.group(1).upper()
            if code not in BAD_CODES and code not in found:
                found.append(code)
    return found[:5]


def make_record(brand, domain, category, source_url, destination, content, code=""):
    discount_match = DISCOUNT_RE.search(content)
    discount = discount_match.group(0) if discount_match else ""
    digest = hashlib.sha256(f"{domain}|{brand}|{code}|{content}".encode("utf-8")).hexdigest()[:16]
    return {
        "id": digest,
        "title": f"{brand} — {discount or ('Coupon code ' + code if code else 'Official promotion')}",
        "content": content,
        "code": code,
        "discount": discount,
        "merchant": brand,
        "category": category,
        "country": "International",
        "url": destination,
        "source_url": source_url,
        "promotion_url": destination,
        "source_label": f"{brand} Official Promotions",
        "source_domain": domain,
        "official_source": True,
        "code_context": bool(code),
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "last_checked": datetime.now(timezone.utc).isoformat(),
        "expires_at": parse_expiry(content) or "",
        "status": "active",
        "verified": False,
        "verification_method": "official_merchant_page_scalable",
        "images": [],
        "image": "",
        "summary_type": "official_merchant_promotion_discovery",
        "expanded_source_collector": True,
        "scalable_collector": True,
    }


def scan(entry):
    brand = str(entry.get("name", "")).strip()
    domain = str(entry.get("domain", "")).strip().lower().removeprefix("www.")
    category = CATEGORY_MAP.get(str(entry.get("category", "")), str(entry.get("category", "")))
    root = official_url(domain)
    if not brand or not domain or not root:
        return brand, [], "invalid_catalog_entry"
    try:
        first_url, first_html = fetch(root)
        pages = [(first_url, first_html)]
        for candidate in candidate_links(first_url, first_html, domain):
            try:
                final_url, html = fetch(candidate)
                pages.append((final_url, html))
            except Exception:
                continue
        all_records = []
        for page_url, html in pages:
            page_text = clean(html)
            page_blocks = blocks(html)
            found_codes = codes(page_text)
            for code in found_codes:
                context = next((b for b in page_blocks if code.lower() in b.lower()), f"Official promotion code {code} published on the merchant's official website.")
                destination = page_url if re.search(r"shop|product|collection|sale|deal|offer|promo|coupon", urlparse(page_url).path, re.I) else ""
                if not destination:
                    destination = next((u for u in candidate_links(page_url, html, domain) if re.search(r"shop|product|collection|sale|deal|offer", urlparse(u).path, re.I)), "")
                if destination:
                    all_records.append(make_record(brand, domain, category, page_url, destination, context, code))
            for text in page_blocks:
                if found_codes and any(code.lower() in text.lower() for code in found_codes):
                    continue
                destination = page_url if re.search(r"shop|product|collection|sale|deal|offer|promo|coupon", urlparse(page_url).path, re.I) else ""
                if destination:
                    all_records.append(make_record(brand, domain, category, page_url, destination, text))
        unique = {}
        for record in all_records:
            key = (record["merchant"].lower(), record["code"].upper(), re.sub(r"\W+", " ", record["content"].lower()).strip())
            unique[key] = record
        return brand, list(unique.values())[:MAX_BLOCKS], "ok"
    except Exception as exc:
        return brand, [], f"error:{type(exc).__name__}"


def main():
    catalog = load_catalog()
    entries = []
    for category, values in catalog.items():
        for value in values if isinstance(values, list) else []:
            item = dict(value)
            item["category"] = category
            entries.append(item)
    entries = entries[:MAX_BRANDS]
    existing = load_items()
    # Only replace records produced by this scalable collector after a successful scan.
    retained = [x for x in existing if not x.get("scalable_collector")]
    scanned = 0
    successful = 0
    failed = 0
    added = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(scan, entry): entry for entry in entries}
        for future in as_completed(futures):
            scanned += 1
            brand, records, status = future.result()
            if status == "ok":
                successful += 1
                retained.extend(records)
                added += len(records)
            else:
                failed += 1
                print(f"SCALABLE SOURCE {status}: {brand}")
    dedup = {}
    for item in retained:
        key = (str(item.get("merchant", "")).strip().lower(), str(item.get("code", "")).strip().upper(), re.sub(r"\s+", " ", str(item.get("content", "")).strip().lower()))
        if key[0]:
            dedup[key] = item
    output = list(dedup.values())[-6000:]
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SCALABLE BRAND SCAN: capacity={MAX_BRANDS}, catalog={len(entries)}, scanned={scanned}, successful={successful}, failed={failed}, records_added={added}, total_records={len(output)}")


if __name__ == "__main__":
    main()
