import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from catalog_utils import canonicalize_item, category_for_brand
from news_bot import SOURCES, HEADERS, clean, parse_expiry, is_official_source, EXPLICIT_CODE_PATTERNS, BAD_CODES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
MAX_BLOCKS_PER_SOURCE = 8
PROMO_WORDS = re.compile(r"\b(?:sale|promotion|promotions|offer|offers|deal|deals|discount|save|savings|special offer|limited time|clearance|member offer)\b", re.I)
DISCOUNT_RE = re.compile(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%\s?off|\d{1,3}%\s?discount|save\s+\$?\d+(?:\.\d+)?)", re.I)


def load():
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def expired(item):
    if str(item.get("status", "active")).lower() in {"expired", "inactive"}:
        return True
    raw = str(item.get("expires_at", "")).strip()
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= datetime.now(timezone.utc)
    except ValueError:
        return False


def has_explicit_code(text):
    for pattern in EXPLICIT_CODE_PATTERNS:
        for match in pattern.findall(text):
            code = match.upper()
            if code not in BAD_CODES:
                return True
    return False


def extract_links(html, source):
    if not is_official_source(source):
        return []
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    seen_text = set()
    for tag in soup.find_all(["article", "li", "div", "section"]):
        text = clean(tag.get_text(" ", strip=True))
        if not (30 <= len(text) <= 900):
            continue
        if not PROMO_WORDS.search(text) or has_explicit_code(text):
            continue
        if not (DISCOUNT_RE.search(text) or re.search(r"\b(?:promotion|promotions|special offer|limited time|clearance)\b", text, re.I)):
            continue
        if text in seen_text:
            continue
        seen_text.add(text)
        blocks.append(text)
        if len(blocks) >= MAX_BLOCKS_PER_SOURCE:
            break

    results = []
    category = category_for_brand(source["merchant"]) or source["category"]
    for block in blocks:
        discount = DISCOUNT_RE.search(block)
        results.append({
            "id": hashlib.sha256((source["name"] + "|promotion|" + block[:300]).encode()).hexdigest()[:16],
            "title": f"{source['merchant']} — {discount.group(0) if discount else 'Official promotion'}",
            "content": block[:500],
            "code": "",
            "discount": discount.group(0) if discount else "",
            "merchant": source["merchant"],
            "category": category,
            "country": "International",
            "url": source["url"],
            "source_url": source["url"],
            "promotion_url": source["url"],
            "source_label": source["name"],
            "source_domain": source["domain"],
            "official_source": True,
            "code_context": False,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "expires_at": parse_expiry(block),
            "status": "active",
            "verified": False,
            "verification_method": "official_merchant_page",
            "images": [],
            "image": "",
            "summary_type": "official_merchant_promotion_discovery",
        })
    return results


def main():
    existing = [canonicalize_item(x) for x in load() if not expired(x)]
    by_id = {str(x.get("id")): x for x in existing if x.get("id")}
    discovered = 0
    errors = 0
    for source in SOURCES:
        if not is_official_source(source):
            continue
        try:
            response = requests.get(source["url"], headers=HEADERS, timeout=25)
            response.raise_for_status()
            for deal in extract_links(response.text, source):
                deal = canonicalize_item(deal)
                old = by_id.get(deal["id"])
                if old:
                    old.update({"merchant": deal["merchant"], "category": deal["category"], "content": deal["content"], "discount": deal["discount"], "last_checked": deal["last_checked"], "status": "active", "promotion_url": deal["promotion_url"]})
                    if deal.get("expires_at"):
                        old["expires_at"] = deal["expires_at"]
                else:
                    by_id[deal["id"]] = deal
                    discovered += 1
        except Exception as exc:
            errors += 1
            print(f"PROMOTION SOURCE ERROR {source['name']}: {exc}")

    data = [canonicalize_item(x) for x in by_id.values()]
    data.sort(key=lambda x: x.get("last_checked", ""), reverse=True)
    OUT.write_text(json.dumps(data[:1200], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PROMOTION LINKS DONE: discovered={discovered}, source_errors={errors}, total={len(data[:1200])}")


if __name__ == "__main__":
    main()
