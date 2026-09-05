"""Live gate for the assistant-verified 4-category merchant source pool.

Rules:
- exactly 30 selected merchants per category;
- candidates are considered by ascending research rank;
- failed candidates are skipped and the next verified candidate is promoted;
- only assistant-marked verified_first_party entries are eligible;
- official-domain identity and live commerce/purchase signals are required;
- if any category cannot reach 30, the workflow fails and nothing is publishable.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = [
    ROOT / "data" / "assistant_verified_sources.json",
    ROOT / "data" / "assistant_verified_electronics_additions.json",
    ROOT / "data" / "assistant_verified_beauty_additions.json",
    ROOT / "data" / "assistant_verified_home_additions.json",
]
EXPECTED = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]
UA = "Mozilla/5.0 (compatible; Deal24HSourceGate/1.0; +https://deal24h.net/)"
TIMEOUT = 20
CTA = re.compile(r"\b(add to cart|add to bag|buy now|shop now|shop all|purchase|checkout|order now|mua ngay|thêm vào giỏ|đặt hàng)\b", re.I)
COMMERCE = re.compile(r"/shop(?:/|$)|/store(?:/|$)|/products?(?:/|$)|/p/|/sale(?:/|$)|/deals?(?:/|$)|/offers?(?:/|$)|/promotions?(?:/|$)", re.I)

def host(value):
    p = urlparse(value if "://" in str(value) else "https://" + str(value))
    return (p.hostname or "").lower().removeprefix("www.")

def same_domain(allowed, actual):
    a, b = host(allowed), host(actual)
    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))

def load():
    rows = []
    for path in MANIFESTS:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        default_category = str(data.get("category", "")).strip()
        for row in data.get("verified_sources", []):
            row = dict(row)
            if default_category and not row.get("category"):
                row["category"] = default_category
            rows.append(row)
    return rows

def verify(row):
    url = str(row.get("official_homepage") or "").strip()
    domain = str(row.get("domain") or "").strip()
    if row.get("verification_status") != "verified_first_party":
        return False, "manifest_status_not_verified"
    if not url or not domain:
        return False, "missing_url_or_domain"
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}, timeout=TIMEOUT, allow_redirects=True)
    except Exception as exc:
        return False, f"request_failed:{type(exc).__name__}"
    if r.status_code >= 400:
        return False, f"http_{r.status_code}"
    final_host = host(r.url)
    if not same_domain(domain, final_host):
        return False, f"redirected_outside_official_domain:{final_host}"
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body = soup.get_text(" ", strip=True)[:120000]
    links = " ".join(a.get("href", "") for a in soup.find_all("a", href=True))
    commerce = bool(COMMERCE.search(r.url) or COMMERCE.search(links) or CTA.search(body))
    identity = str(row.get("name", "")).split("—")[0].strip().lower()
    identity_tokens = [t for t in re.findall(r"[a-z0-9]+", identity) if len(t) >= 3]
    identity_ok = not identity_tokens or any(t in (title + " " + body[:20000]).lower() for t in identity_tokens)
    if not identity_ok:
        return False, "weak_brand_identity_signal"
    if not commerce:
        return False, "no_live_commerce_signal"
    return True, r.url

def main():
    rows = load()
    eligible = [r for r in rows if r.get("verification_status") == "verified_first_party" and str(r.get("category", "")).strip() in EXPECTED]
    selected = {}
    failures = []
    for category in EXPECTED:
        candidates = [r for r in eligible if str(r.get("category", "")).strip() == category]
        candidates.sort(key=lambda r: (int(r.get("rank", 999999)), str(r.get("name", "")).lower()))
        chosen = []
        for row in candidates:
            if len(chosen) >= 30:
                break
            ok, reason = verify(row)
            if ok:
                chosen.append(row)
                print(f"PASS {category} rank={row.get('rank')} {row.get('name')} -> {reason}")
            else:
                failures.append(f"{category} rank={row.get('rank')} {row.get('name')}: {reason}")
                print(f"SKIP {category} rank={row.get('rank')} {row.get('name')}: {reason}")
        selected[category] = chosen
        if len(chosen) < 30:
            failures.append(f"{category}: only {len(chosen)}/30 live verified candidates")

    counts = {k: len(v) for k, v in selected.items()}
    total = sum(counts.values())
    print(f"ASSISTANT SOURCE GATE COUNTS: {counts} total={total}")
    if total != 120 or any(v != 30 for v in counts.values()):
        print("ASSISTANT SOURCE GATE FAILED")
        for failure in failures[:200]:
            print(f"  {failure}")
        raise SystemExit(1)

    out = []
    for category in EXPECTED:
        for row in selected[category]:
            out.append({
                "rank": int(row["rank"]),
                "name": row["name"],
                "merchant": row["name"],
                "category": category,
                "domain": row["domain"],
                "official_homepage": row["official_homepage"],
                "verification_status": "live_verified_first_party",
            })
    (ROOT / "data" / "assistant_verified_source_selection.json").write_text(json.dumps({"schema_version":1,"total":120,"counts":counts,"sources":out}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ASSISTANT SOURCE GATE PASS: 4 categories x 30 = 120 live-verified first-party sources")

if __name__ == "__main__":
    main()
