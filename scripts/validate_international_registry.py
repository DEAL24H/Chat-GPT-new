"""Validate the international DEAL24H first-party brand/merchant registry.

This is intentionally conservative: a domain is not considered publishable merely
because DNS/HTTP works. The script requires a same-domain response and commerce
signals, then records discovered same-domain deal/product links for later crawling.
It never accepts a third-party coupon/deal domain as an official source.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "international_brand_registry.json"
REPORT = ROOT / "data" / "international_source_audit.json"
TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; Deal24HSourceAudit/1.0; +https://deal24h.net/)"
LINK_TERMS = re.compile(r"\b(sale|deals?|offers?|promotion|promotions|discount|clearance|outlet|special prices?|limited offers?)\b", re.I)
PRODUCT_TERMS = re.compile(r"\b(product|products|shop|store|collection|category|buy|p/)\b", re.I)
BAD_TERMS = re.compile(r"\b(privacy|terms|legal|careers|press|investor|support|help|login)\b", re.I)

def host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")

def same_domain(url, expected):
    h = host(url)
    return h == expected or h.endswith("." + expected)

def clean_url(url):
    p = urlparse(url)
    return p._replace(fragment="").geturl()

def audit(entry, category):
    brand = entry["name"]
    domain = entry["domain"].lower().removeprefix("www.")
    root = "https://" + domain + "/"
    result = {
        "name": brand,
        "category": category,
        "domain": domain,
        "official_homepage": root,
        "status": "failed",
        "http_status": None,
        "final_url": "",
        "same_domain": False,
        "commerce_signals": [],
        "deal_sources": [],
        "product_sources": [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "reason": "",
    }
    try:
        r = requests.get(root, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}, timeout=TIMEOUT, allow_redirects=True)
        result["http_status"] = r.status_code
        result["final_url"] = clean_url(r.url)
        result["same_domain"] = same_domain(r.url, domain)
        if r.status_code >= 400:
            result["reason"] = f"HTTP_{r.status_code}"
            return result
        if not result["same_domain"]:
            result["reason"] = "REDIRECTED_OUTSIDE_OFFICIAL_DOMAIN"
            return result
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        og = soup.find("meta", attrs={"property": "og:site_name"})
        site_name = og.get("content", "") if og else ""
        body = soup.get_text(" ", strip=True)[:120000]
        identity = (brand.lower().split(" ")[0] in (title + " " + site_name + " " + body).lower())
        if identity:
            result["commerce_signals"].append("brand_identity")
        links = []
        for a in soup.find_all("a", href=True):
            href = clean_url(urljoin(r.url, a.get("href", "").strip()))
            if not href.startswith(("https://", "http://")) or not same_domain(href, domain):
                continue
            text = a.get_text(" ", strip=True)
            hay = f"{text} {urlparse(href).path} {urlparse(href).query}"
            if BAD_TERMS.search(hay):
                continue
            links.append((text, href))
        for text, href in links:
            if LINK_TERMS.search(f"{text} {href}"):
                result["deal_sources"].append(href)
            if PRODUCT_TERMS.search(f"{text} {href}"):
                result["product_sources"].append(href)
        result["deal_sources"] = list(dict.fromkeys(result["deal_sources"]))[:20]
        result["product_sources"] = list(dict.fromkeys(result["product_sources"]))[:20]
        if result["deal_sources"]:
            result["commerce_signals"].append("same_domain_deal_navigation")
        if result["product_sources"]:
            result["commerce_signals"].append("same_domain_product_navigation")
        if identity and (result["deal_sources"] or result["product_sources"]):
            result["status"] = "verified_first_party"
        elif identity:
            result["status"] = "first_party_identity_only"
            result["reason"] = "NO_DEAL_OR_PRODUCT_NAVIGATION_DISCOVERED"
        else:
            result["reason"] = "BRAND_IDENTITY_NOT_CONFIRMED"
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}:{exc}"
    return result

def main():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    categories = data.get("categories", {})
    results = []
    for category, entries in categories.items():
        for entry in entries:
            results.append(audit(entry, category))
    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_file": str(REGISTRY.relative_to(ROOT)),
        "total": len(results),
        "verified_first_party": sum(x["status"] == "verified_first_party" for x in results),
        "identity_only": sum(x["status"] == "first_party_identity_only" for x in results),
        "failed": sum(x["status"] == "failed" for x in results),
        "results": results,
    }
    REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"INTERNATIONAL SOURCE AUDIT: total={summary['total']} verified={summary['verified_first_party']} identity_only={summary['identity_only']} failed={summary['failed']}")
    if summary["failed"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
