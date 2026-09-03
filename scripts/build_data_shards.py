"""Build browser-friendly data shards and a compact global search index."""
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCE = DATA / "news.json"
OUT = DATA / "shards"
CATEGORY_SLUGS = {"Fashion":"fashion","Beauty":"beauty","Gaming":"gaming","Consumer":"consumer","Home & Living":"home-living","Sports & Outdoor":"sports-outdoor","Food & Grocery":"food-grocery","Travel & Hotels":"travel-hotels","Software & Digital Services":"software-digital-services","Baby, Kids & Family":"baby-kids-family","Automotive & Accessories":"automotive-accessories","Books, Education & Media":"books-education-media"}

def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def stable_id(item):
    raw = str(item.get("id") or "")
    return raw or hashlib.sha1(json.dumps(item, sort_keys=True).encode()).hexdigest()[:16]

def active(item):
    return isinstance(item, dict) and item.get("status") != "expired" and bool(item.get("code") or item.get("promotion_url") or item.get("url"))

def compact(item, shard):
    return {"id":stable_id(item),"title":item.get("title",""),"content":item.get("content",""),"code":item.get("code",""),"discount":item.get("discount",""),"merchant":item.get("merchant",""),"category":item.get("category","") ,"promotion_url":item.get("promotion_url") or item.get("url") or item.get("source_url",""),"official_source":bool(item.get("official_source")),"expires_at":item.get("expires_at",""),"status":item.get("status","active"),"_shard":shard}

def main():
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items", [])
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"): old.unlink()
    shards, search = {}, []
    for item in items:
        if not active(item): continue
        category = item.get("category") or "Consumer"
        slug = CATEGORY_SLUGS.get(category, "consumer")
        row = compact(item, f"shards/{slug}.json")
        shards.setdefault(slug, []).append(row)
        search.append({"id":row["id"],"shard":row["_shard"],"merchant":row["merchant"],"category":row["category"],"text":norm(" ".join([row["merchant"],row["title"],row["code"],row["content"]]))[:600]})
    manifest={"version":1,"shards":{},"search":"search-index.json"}
    for slug, rows in sorted(shards.items()):
        rows.sort(key=lambda x:(norm(x.get("merchant")),x.get("id","")))
        (OUT/f"{slug}.json").write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        manifest["shards"][slug]={"path":f"shards/{slug}.json","count":len(rows)}
    search.sort(key=lambda x:(norm(x["merchant"]),x["id"]))
    (DATA/"search-index.json").write_text(json.dumps({"version":1,"count":len(search),"items":search},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    (DATA/"data-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"Built {len(shards)} data shards and {len(search)} search records")

if __name__ == "__main__": main()
