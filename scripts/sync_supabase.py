"""Synchronize Supabase with the canonical TN01 four-category deal dataset.

Contract:
- exactly four categories: Fashion, Electronics, Beauty & Personal Care, Home & Living
- merchant identity comes only from assistant_verified_source_selection.json
- every published row has a same-merchant final_purchase_url
- promotion_url and url are aliases of final_purchase_url
- Supabase public.deals is the only PostgREST write target; PostgreSQL routes to partitions
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SELECTION = ROOT / "data" / "assistant_verified_source_selection.json"
CATEGORIES = ("Fashion", "Electronics", "Beauty & Personal Care", "Home & Living")


def normalize_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    suffix = "/rest/v1"
    if raw.lower().endswith(suffix):
        raw = raw[: -len(suffix)].rstrip("/")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("SUPABASE_URL must be a valid project URL")
    return raw


URL = normalize_base_url(os.getenv("SUPABASE_URL", ""))
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
if not URL or not KEY:
    raise SystemExit("Supabase sync requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")

selection = json.loads(SELECTION.read_text(encoding="utf-8"))
if selection.get("total") != 120 or selection.get("counts") != {c: 30 for c in CATEGORIES}:
    raise SystemExit(f"Supabase contract: invalid assistant source selection {selection.get('counts')}")
if selection.get("source_authority") != "assistant_verified_manifests":
    raise SystemExit("Supabase contract: unexpected source authority")

allowed = {
    (str(row.get("merchant") or "").casefold(), str(row.get("category") or "")): row
    for row in selection.get("sources", [])
}
if len(allowed) != 120:
    raise SystemExit(f"Supabase contract: expected 120 unique assistant-verified merchants, found {len(allowed)}")

raw = json.loads(DATA.read_text(encoding="utf-8"))
items = raw if isinstance(raw, list) else raw.get("items", [])
rows = []
for x in items:
    if not isinstance(x, dict) or x.get("status") == "expired":
        continue
    merchant = str(x.get("merchant") or "").strip()
    category = str(x.get("category") or "").strip()
    if category not in CATEGORIES:
        raise SystemExit(f"Supabase contract: non-canonical category for {merchant}: {category}")
    source = allowed.get((merchant.casefold(), category))
    if not source:
        raise SystemExit(f"Supabase contract: merchant is outside assistant allowlist: {merchant} / {category}")

    final_purchase_url = str(x.get("final_purchase_url") or "").strip()
    promotion_url = str(x.get("promotion_url") or "").strip()
    url = str(x.get("url") or "").strip()
    if not final_purchase_url or promotion_url != final_purchase_url or url != final_purchase_url:
        raise SystemExit(f"Supabase contract: inconsistent purchase destination for {merchant}")
    if x.get("source_verification_status") != "assistant_verified_first_party":
        raise SystemExit(f"Supabase contract: source not assistant-verified for {merchant}")
    purchase_status = x.get("purchase_url_verification_status")
    if purchase_status not in {"live_verified", "runtime_inaccessible"}:
        raise SystemExit(f"Supabase contract: purchase URL verification missing for {merchant}: {purchase_status}")

    rows.append({
        "id": str(x.get("id") or ""),
        "merchant": merchant,
        "category": category,
        "country": x.get("country") or "International",
        "title": x.get("title"),
        "content": x.get("content"),
        "code": x.get("code"),
        "discount": x.get("discount"),
        "promotion_url": final_purchase_url,
        "source_url": x.get("source_url"),
        "source_domain": source.get("domain"),
        "official_source": True,
        "status": x.get("status") or "active",
        "expires_at": x.get("expires_at") or None,
        "detected_at": x.get("detected_at") or None,
        "last_checked": x.get("last_checked") or None,
        "final_purchase_url": final_purchase_url,
        "source_verification_status": "assistant_verified_first_party",
        "source_verification_authority": "assistant",
        "purchase_url_verification_status": purchase_status,
        "purchase_url_verification_reason": x.get("purchase_url_verification_reason"),
        "purchase_url_verified_at": x.get("purchase_url_verified_at") or None,
    })
    if not rows[-1]["id"]:
        raise SystemExit(f"Supabase contract: empty deal id for {merchant}")

by_category = {category: [] for category in CATEGORIES}
for row in rows:
    by_category[row["category"]].append(row)

headers = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}


def request(method, table="deals", body=None, query="", prefer=None):
    endpoint = f"{URL}/rest/v1/{table}{query}"
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req_headers = dict(headers)
    if prefer:
        req_headers["Prefer"] = prefer
    req = urllib.request.Request(endpoint, data=payload, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Supabase {method} {endpoint} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Supabase {method} {endpoint} failed: {exc.reason}") from exc


def exact_count(query=""):
    _, response_headers, _ = request("GET", "deals", query=f"?select=id&limit=1{query}", prefer="count=exact")
    content_range = response_headers.get("Content-Range", "")
    if "/" not in content_range:
        raise RuntimeError("Supabase deals: missing Content-Range verification header")
    return int(content_range.rsplit("/", 1)[1])


ids = [r["id"] for r in rows]
if rows:
    request("POST", "deals", rows)
if ids:
    encoded = ",".join(urllib.parse.quote(i, safe="") for i in ids)
    request("DELETE", "deals", query=f"?id=not.in.({encoded})")
else:
    request("DELETE", "deals", query="?id=not.is.null")

actual_total = exact_count()
if actual_total != len(rows):
    raise RuntimeError(f"Supabase deals: expected {len(rows)} rows, found {actual_total}")

for category in CATEGORIES:
    expected = len(by_category[category])
    encoded_category = urllib.parse.quote(category, safe="")
    actual = exact_count(f"&category=eq.{encoded_category}")
    if actual != expected:
        raise RuntimeError(f"Supabase deals category {category!r}: expected {expected} rows, found {actual}")

print("SUPABASE CANONICAL SYNC PASS:", f"deals={actual_total}", ", ".join(f"{c}={len(by_category[c])}" for c in CATEGORIES))
