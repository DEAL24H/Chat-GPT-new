"""Audit international first-party sources and select the first 30 eligible per category.

Eligibility is deliberately conservative: the official domain must resolve without
leaving the domain, the brand identity must be evidenced by multiple page signals,
and the site must expose same-domain commerce navigation. Failed candidates are
replaced by the next ranked candidate; no third-party coupon domain is accepted.
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
UA = "Mozilla/5.0 (compatible; Deal24HSourceAudit/2.0; +https://deal24h.net/)"
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


def identity_evidence(brand, title, site_name, canonical, body):
    """Require stronger evidence than a first-word substring match."""
    b = re.sub(r"[^a-z0-9]+", " ", brand.lower()).strip()
    parts = [re.sub(r"[^a-z0-9]+", " ", x.lower()).strip() for x in (title, site_name, canonical)]
    exact = sum(bool(b and (b == x or b in x)) for x in parts)
    first = re.sub(r"[^a-z0-9]+", " ", brand.lower()).split()[0] if brand else ""
    body_match = bool(first and re.search(rf"\b{re.escape(first)}\b", body.lower()))
    return exact >= 1 and body_match


def audit(entry, category, source_rank):
    brand = entry["name"]
    domain = entry["domain"].lower().removeprefix("www.")
    root = "https://" + domain + "/"
    result = {
        "rank": source_rank,
        "name": brand,
        "category": category,
        "domain": domain,
        "official_homepage": root,
        "status": "failed",
        "http_status": None,
        "final_url": "",
        "same_domain": False,
        "identity_evidence": [],
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
        canonical_tag = soup.find("link", attrs={"rel": lambda x: x and "canonical" in x})
        canonical = canonical_tag.get("href", "") if canonical_tag else r.url
        body = soup.get_text(" ", strip=True)[:120000]
        if title:
            result["identity_evidence"].append("title") if brand.lower() in title.lower() else None
        if site_name:
            result["identity_evidence"].append("og_site_name") if brand.lower() in site_name.lower() else None
        if canonical and same_domain(canonical, domain):
            result["identity_evidence"].append("canonical_official_domain")
        identity = identity_evidence(brand, title, site_name, canonical, body)
        if identity:
            result["commerce_signals"].append("brand_identity_confirmed")
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


def candidate_entries(category_data):
    """Return ranked candidates with duplicates removed, preserving first occurrence."""
    combined = list(category_data.get("entries", [])) + list(category_data.get("candidate_pool", []))
    seen = set()
    out = []
    for fallback_rank, entry in enumerate(combined, 1):
        key = (str(entry.get("name", "")).strip().lower(), str(entry.get("domain", "")).strip().lower())
        if not key[0] or key in seen:
            continue
        seen.add(key)
        item = dict(entry)
        item["rank"] = int(item.get("rank", fallback_rank))
        out.append(item)
    out.sort(key=lambda x: x["rank"])
    return out


def main():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    raw_categories = data.get("categories", {})
    results = []
    selected = {}
    selection_log = {}
    for category, category_data in raw_categories.items():
        if isinstance(category_data, list):
            category_data = {"entries": category_data, "candidate_pool": []}
        candidates = candidate_entries(category_data)
        category_results = []
        for entry in candidates:
            audit_result = audit(entry, category, entry["rank"])
            category_results.append(audit_result)
            results.append(audit_result)
        eligible = [x for x in category_results if x["status"] == "verified_first_party"]
        chosen = eligible[:30]
        selected[category] = [{"rank": x["rank"], "name": x["name"], "domain": x["domain"]} for x in chosen]
        selection_log[category] = {
            "candidate_count": len(candidates),
            "eligible_count": len(eligible),
            "selected_count": len(chosen),
            "promoted_ranks": [x["rank"] for x in chosen if x["rank"] > 30],
            "meets_target": len(chosen) == 30,
        }
    failed = sum(x["status"] == "failed" for x in results)
    identity_only = sum(x["status"] == "first_party_identity_only" for x in results)
    verified = sum(x["status"] == "verified_first_party" for x in results)
    target_failures = [c for c, info in selection_log.items() if not info["meets_target"]]
    summary = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_file": str(REGISTRY.relative_to(ROOT)),
        "selection_rule": "first 30 eligible by international search-demand rank; failed/ineligible candidates are replaced by the next ranked candidate",
        "total_candidates_audited": len(results),
        "verified_first_party": verified,
        "identity_only": identity_only,
        "failed": failed,
        "target_categories_without_30_eligible": target_failures,
        "selection": selection_log,
        "selected": selected,
        "results": results,
    }
    REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"INTERNATIONAL SOURCE AUDIT: candidates={len(results)} verified={verified} identity_only={identity_only} failed={failed} categories_short={len(target_failures)}")
    if target_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
