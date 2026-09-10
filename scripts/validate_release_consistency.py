"""Validate the generated static publication layers describe one release."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://deal24h.net"

def main():
    errors = []
    data = ROOT / "data"
    manifest = json.loads((data / "data-manifest.json").read_text(encoding="utf-8"))
    search = json.loads((data / "search-index.json").read_text(encoding="utf-8"))
    if manifest.get("total") != search.get("count") or manifest.get("total") != len(search.get("items", [])):
        errors.append("STATIC_MANIFEST_SEARCH_COUNT_MISMATCH")
    shard_total = 0
    for slug, info in manifest.get("shards", {}).items():
        path = data / info["path"]
        if not path.exists():
            errors.append(f"MISSING_SHARD:{slug}")
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        if len(rows) != info.get("count"):
            errors.append(f"SHARD_COUNT_MISMATCH:{slug}")
        shard_total += len(rows)
    if shard_total != manifest.get("total"):
        errors.append(f"SHARD_TOTAL_MISMATCH:{shard_total}:{manifest.get('total')}")
    seo_index = json.loads((ROOT / "seo" / "seo-index.json").read_text(encoding="utf-8"))
    seo_urls = {str(x.get("canonical")) for x in seo_index.get("offers", []) if x.get("canonical")}
    sitemap = (ROOT / "sitemap-seo.xml").read_text(encoding="utf-8")
    sitemap_urls = set(re.findall(r"<loc>(https://deal24h\.net/seo/[^<]+/)</loc>", sitemap))
    if seo_urls != sitemap_urls:
        errors.append(f"SEO_SITEMAP_MISMATCH:missing={len(seo_urls-sitemap_urls)}:extra={len(sitemap_urls-seo_urls)}")
    main_sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    if not seo_urls.issubset(set(re.findall(r"<loc>(https://deal24h\.net/[^<]+/)</loc>", main_sitemap))):
        errors.append("MAIN_SITEMAP_MISSING_SEO_URL")
    if errors:
        print("RELEASE CONSISTENCY FAILED")
        for error in errors:
            print("-", error)
        raise SystemExit(1)
    print(f"RELEASE CONSISTENCY PASS: static_records={manifest.get('total')} seo_pages={len(seo_urls)} sitemap_layers=consistent")

if __name__ == "__main__":
    main()
