"""Audit assistant-verified first-party sources and select the first 30 eligible per category.

The research registry provides the ranked brand list.  The assistant-verified manifests are
an explicit execution allowlist: the bot may only use sources that were researched and
verified by the assistant.  The live audit then checks that each approved official
commerce URL is reachable and still exposes first-party identity plus commerce
navigation. Failed candidates are replaced by the next assistant-verified candidate.
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
ASSISTANT_MANIFESTS = [
    ROOT / "data" / "assistant_verified_sources.json",
    ROOT / "data" / "assistant_verified_electronics_additions.json",
    ROOT / "data" / "assistant_verified_beauty_additions.json",
    ROOT / "data" / "assistant_verified_home_additions.json",
]
TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; Deal24HSourceAudit/3.0; +https://deal24h.net/)"
LINK_TERMS = re.compile(r"\b(sale|deals?|offers?|promotion|promotions|discount|clearance|outlet|special prices?|limited offers?)\b", re.I)
PRODUCT_TERMS = re.compile(r"\b(product|products|shop|store|collection|category|buy|p/)\b", re.I)
BAD_TERMS = re.compile(r"\b(privacy|terms|legal|careers|press|investor|support|help|login)\b", re.I)


def host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def same_domain(url, expected):
    h = host(url)
    e = expected.lower().removeprefix("www.")
    return h == e or h.endswith("." + e)


def clean_url(url):
    p = urlparse(url)
    return p._replace(fragment="").geturl()


def identity_evidence(brand, title, site_name, canonical, body):
    """Require meaningful brand evidence rather than an accidental substring match."""
    b = re.sub(r"[^a-z0-9]+", " ", brand.lower()).strip()
    parts = [re.sub(r"[^a-z0-9]+", " ", x.lower()).strip() for x in (title, site_name, canonical)]
    exact = sum(bool(b and (b == x or b in x)) for x in parts)
    first = re.sub(r"[^a-z0-9]+", " ", brand.lower()).split()[0] if brand else ""
    body_match = bool(first and re.search(rf"\b{re.escape(first)}\b", body.lower()))
    return exact >= 1 and body_match


def load_assistant_verified():
    """Load only sources explicitly verified by the assistant."""
    out = []
    for path in ASSISTANT_MANIFESTS:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        default_category = data.get("category")
        for item in data.get("verified_sources", []):
            if item.get("verification_status") != "verified_first_party":
                continue
            row = dict(item)
            row["category"] = row.get("category") or default_category
            if row.get("official_homepage"):
                row["official_homepage"] = clean_url(row["official_homepage"])
            out.append(row)
    # First occurrence wins. This prevents duplicate manifests from changing rank/order.
    seen = set()
    unique = []
    for row in out:
        key = (row.get("category", ""), row.get("name", "").strip().lower(), row.get("domain", "").strip().lower())
        if key in seen or not key[1]:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def load_ranked_registry():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    categories = data.get("categories", {})
    ranked = {}
    for category, category_data in categories.items():
        entries = category_data if isinstance(category_data, list) else category_data.get("entries", [])
        ranked[category] = {x.get("name", "").strip().lower(): int(x.get("rank", 9999)) for x in entries}
    return ranked


def candidate_entries(category, verified_sources, ranked_registry):
    """Use the assistant-verified allowlist, ordered by research rank then backup rank."""
    rows = [x for x in verified_sources if x.get("category") == category]
    registry_ranks = ranked_registry.get(category, {})
    def sort_key(x):
        name = x.get("name", "").strip().lower()
        # Preserve the researched rank where present. Backups keep their manifest rank.
        return (int(x.get("rank", registry_ranks.get(name, 9999))), name)
    rows.sort(key=sort_key)
    return rows


def audit(entry, category, source_rank):
    brand = entry["name"]
    declared_domain = entry.get("domain", "").lower().removeprefix("www.")
    configured_homepage = entry.get("official_homepage") or ("https://" + declared_domain + "/")
    root = clean_url(configured_homepage)
    expected_domain = host(root) or declared_domain
    result = {
        "rank": source_rank,
        "name": brand,
        "category": category,
        "domain": declared_domain,
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
        result["same_domain"] = same_domain(r.url, expected_domain)
        if r.status_code >= 400:
            result["reason"] = f"HTTP_{r.status_code}"
            return result
        if not result["same_domain"]:
            result["reason"] = "REDIRECTED_OUTSIDE_VERIFIED_OFFICIAL_DOMAIN"
            return result
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        og = soup.find("meta", attrs={"property": "og:site_name"})
        site_name = og.get("content", "") if og else ""
        canonical_tag = soup.find("link", attrs={"rel": lambda x: x and "canonical" in x})
        canonical = canonical_tag.get("href", "") if canonical_tag else r.url
        body = soup.get_text(" ", strip=True)[:120000]
        if title and brand.lower() in title.lower():
            result["identity_evidence"].append("title")
        if site_name and brand.lower() in site_name.lower():
            result["identity_evidence"].append("og_site_name")
        if canonical and same_domain(canonical, expected_domain):
            result["identity_evidence"].append("canonical_official_domain")
        identity = identity_evidence(brand, title, site_name, canonical, body)
        if identity:
            result["commerce_signals"].append("brand_identity_confirmed")
        links = []
        for a in soup.find_all("a", href=True):
            href = clean_url(urljoin(r.url, a.get("href", "").strip()))
            if not href.startswith(("https://", "http://")) or not same_domain(href, expected_domain):
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
    ranked_registry = load_ranked_registry()
    verified_sources = load_assistant_verified()
    expected_categories = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]
    results = []
    selected = {}
    selection_log = {}
    for category in expected_categories:
        candidates = candidate_entries(category, verified_sources, ranked_registry)
        category_results = []
        for entry in candidates:
            audit_result = audit(entry, category, int(entry.get("rank", 9999)))
            category_results.append(audit_result)
            results.append(audit_result)
        eligible = [x for x in category_results if x["status"] == "verified_first_party"]
        chosen = eligible[:30]
        selected[category] = [{"rank": x["rank"], "name": x["name"], "domain": x["domain"], "official_homepage": x["official_homepage"]} for x in chosen]
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
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_file": str(REGISTRY.relative_to(ROOT)),
        "execution_allowlist": [str(x.relative_to(ROOT)) for x in ASSISTANT_MANIFESTS if x.exists()],
        "selection_rule": "assistant-verified first-party candidates in ascending researched rank; failed/ineligible candidates are replaced by the next verified candidate",
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
