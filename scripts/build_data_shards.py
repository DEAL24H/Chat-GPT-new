"""Build browser-friendly data shards and a compact global search index."""
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCE = DATA / "news.json"
OUT = DATA / "shards"
CATEGORY_SLUGS = {
    "Fashion": "fashion",
    "Beauty": "beauty",
    "Consumer": "consumer",
    "Home & Living": "home-and-living",
    "Food & Grocery": "food-and-grocery",
    "Travel & Hotels": "travel-and-hotels",
}


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def stable_id(item):
    raw = str(item.get("id") or "")
    return raw or hashlib.sha1(json.dumps(item, sort_keys=True).encode()).hexdigest()[:16]


def active(item):
    return isinstance(item, dict) and item.get("status") != "expired" and bool(
        item.get("code") or item.get("final_purchase_url") or item.get("promotion_url") or item.get("url")
    )


def compact(item, shard):
    destination = item.get("final_purchase_url") or item.get("promotion_url") or item.get("url") or ""
    return {
        "id": stable_id(item),
        "title": item.get("title", ""),
        "content": item.get("content", ""),
        "code": item.get("code", ""),
        "discount": item.get("discount", ""),
        "merchant": item.get("merchant", ""),
        "category": item.get("category", ""),
        "final_purchase_url": destination,
        "promotion_url": destination,
        "official_source": bool(item.get("official_source")),
        "expires_at": item.get("expires_at", ""),
        "status": item.get("status", "active"),
        "_shard": shard,
    }


def main():
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items", [])
    OUT.mkdir(parents=True, exist_ok=True)

    for old in OUT.glob("*.json"):
        old.unlink()

    shards = {slug: [] for slug in CATEGORY_SLUGS.values()}
    search = []
    skipped_categories = set()
    for item in items:
        if not active(item):
            continue
        category = item.get("category") or ""
        shard_slug = CATEGORY_SLUGS.get(category)
        if not shard_slug:
            if category:
                skipped_categories.add(str(category))
            continue
        row = compact(item, f"shards/{shard_slug}.json")
        shards[shard_slug].append(row)
        search.append({
            "id": row["id"],
            "shard": row["_shard"],
            "merchant": row["merchant"],
            "category": row["category"],
            "text": norm(" ".join([row["merchant"], row["title"], row["code"], row["content"]]))[:600],
        })

    manifest = {"version": 2, "categories": list(CATEGORY_SLUGS), "shards": {}, "search": "search-index.json"}
    for category, shard_slug in CATEGORY_SLUGS.items():
        rows = shards[shard_slug]
        rows.sort(key=lambda x: (norm(x.get("merchant")), x.get("id", "")))
        (OUT / f"{shard_slug}.json").write_text(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        manifest["shards"][shard_slug] = {
            "path": f"shards/{shard_slug}.json",
            "count": len(rows),
            "category": category,
        }

    search.sort(key=lambda x: (norm(x["merchant"]), x["id"]))
    (DATA / "search-index.json").write_text(
        json.dumps({"version": 1, "count": len(search), "items": search}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (DATA / "data-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    ignored = f"; skipped non-priority categories: {', '.join(sorted(skipped_categories))}" if skipped_categories else ""
    print(f"Built {sum(bool(v) for v in shards.values())} active data shards, {len(shards)} total category shards and {len(search)} search records{ignored}")


if __name__ == "__main__":
    main()
