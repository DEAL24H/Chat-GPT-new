"""Synchronize Supabase as a mirror of the canonical data/news.json.

The browser data and Supabase must be derived from the same canonical dataset.
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
URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

CATEGORY_TABLES = {
    "Fashion": "deals_fashion",
    "Beauty": "deals_beauty",
    "Consumer": "deals_consumer",
    "Home & Living": "deals_home_living",
    "Food & Grocery": "deals_food_grocery",
    "Travel & Hotels": "deals_travel_hotels",
}

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

headers = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}


def request(method, table, body=None, query=""):
    endpoint = f"{URL}/rest/v1/{table}{query}"
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.status


def sync_table(table, table_rows):
    ids = [r["id"] for r in table_rows]
    # Upsert first so a failed later cleanup cannot destroy the existing mirror.
    if table_rows:
        request("POST", table, table_rows)
    if ids:
        # Remove records that no longer exist in canonical news.json.
        encoded = ",".join(urllib.parse.quote(i, safe="") for i in ids)
        request("DELETE", table, query=f"?id=not.in.({encoded})")
    else:
        request("DELETE", table, query="?id=not.is.null")


by_category = {category: [] for category in CATEGORY_TABLES}
for row in rows:
    by_category.setdefault(row["category"], []).append(row)

# Canonical all-deals mirror.
sync_table("deals", rows)

# Category tables are strict mirrors of the same canonical rows.
for category, table in CATEGORY_TABLES.items():
    sync_table(table, by_category.get(category, []))

print(
    "Supabase canonical sync OK:",
    f"deals={len(rows)}",
    ", ".join(f"{category}={len(by_category.get(category, []))}" for category in CATEGORY_TABLES),
)
