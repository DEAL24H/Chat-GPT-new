"""Synchronize Supabase as a mirror of canonical data/news.json.

Supabase uses public.deals as the canonical partitioned table. The six
category names (deals_fashion, deals_beauty, ...) are PostgreSQL partitions,
not independent PostgREST API resources. Inserts/deletes against public.deals
are automatically routed to the correct partition, so the bot must never call
those partition names through /rest/v1.

The browser data and Supabase are derived from the same canonical dataset.
The public browser never receives the service-role key.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"

CATEGORIES = (
    "Fashion",
    "Beauty",
    "Consumer",
    "Home & Living",
    "Food & Grocery",
    "Travel & Hotels",
)


def normalize_base_url(value: str) -> str:
    """Accept either a Supabase project URL or a URL ending in /rest/v1."""
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
    print("Supabase sync skipped: credentials are not configured.")
    raise SystemExit(0)

raw = json.loads(DATA.read_text(encoding="utf-8"))
items = raw if isinstance(raw, list) else raw.get("items", [])
rows = []
for x in items:
    if not isinstance(x, dict) or x.get("status") == "expired":
        continue
    row = {
        "id": str(x.get("id") or ""),
        "merchant": x.get("merchant") or "Unknown",
        "category": x.get("category") or "Consumer",
        "country": x.get("country"),
        "title": x.get("title"),
        "content": x.get("content"),
        "code": x.get("code"),
        "discount": x.get("discount"),
        "promotion_url": x.get("promotion_url") or x.get("url"),
        "source_url": x.get("source_url"),
        "source_domain": x.get("source_domain"),
        "official_source": bool(x.get("official_source")),
        "status": x.get("status") or "active",
        "expires_at": x.get("expires_at") or None,
        "detected_at": x.get("detected_at") or None,
        "last_checked": x.get("last_checked") or None,
    }
    if row["id"]:
        rows.append(row)

by_category = {category: [] for category in CATEGORIES}
for row in rows:
    category = row["category"]
    if category in by_category:
        by_category[category].append(row)

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
        safe_endpoint = f"{URL}/rest/v1/{table}{query}"
        raise RuntimeError(
            f"Supabase {method} {safe_endpoint} failed: HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Supabase {method} {endpoint} failed: {exc.reason}") from exc


def sync_canonical_table(table_rows):
    ids = [r["id"] for r in table_rows]
    # Upsert first so a failed cleanup cannot destroy the existing mirror.
    if table_rows:
        request("POST", "deals", table_rows)
    if ids:
        encoded = ",".join(urllib.parse.quote(i, safe="") for i in ids)
        request("DELETE", "deals", query=f"?id=not.in.({encoded})")
    else:
        request("DELETE", "deals", query="?id=not.is.null")


def exact_count(query=""):
    _, response_headers, _ = request(
        "GET",
        "deals",
        query=f"?select=id&limit=1{query}",
        prefer="count=exact",
    )
    content_range = response_headers.get("Content-Range", "")
    if "/" not in content_range:
        raise RuntimeError("Supabase deals: missing Content-Range verification header")
    try:
        return int(content_range.rsplit("/", 1)[1])
    except ValueError as exc:
        raise RuntimeError(f"Supabase deals: invalid Content-Range: {content_range}") from exc


# The only PostgREST resource written by this job is public.deals.
# PostgreSQL automatically routes rows into the six category partitions.
sync_canonical_table(rows)
actual_total = exact_count()
if actual_total != len(rows):
    raise RuntimeError(f"Supabase deals: expected {len(rows)} rows, found {actual_total}")

# Verify each category through the parent table. This also proves the
# partition routing worked without touching partition names through PostgREST.
for category in CATEGORIES:
    expected = len(by_category[category])
    encoded_category = urllib.parse.quote(category, safe="")
    actual = exact_count(f"&category=eq.{encoded_category}")
    if actual != expected:
        raise RuntimeError(
            f"Supabase deals category {category!r}: expected {expected} rows, found {actual}"
        )

print(
    "Supabase canonical partition sync + verification OK:",
    f"deals={actual_total}",
    ", ".join(f"{category}={len(by_category[category])}" for category in CATEGORIES),
)
