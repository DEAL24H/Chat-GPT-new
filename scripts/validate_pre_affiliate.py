"""Validate the fixed-scope, affiliate-neutral publication contract."""
import json
import re
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://deal24h.net"

class HTMLAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.robots = ""
        self.canonical = ""
        self.text_parts = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "robots":
            self.robots = attrs.get("content", "")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href", "")
        if tag == "a" and attrs.get("href"):
            self.links.append((attrs.get("href", ""), attrs.get("rel", "")))
    def handle_data(self, data):
        self.text_parts.append(data)
    @property
    def text(self):
        return " ".join(self.text_parts)

def main():
    errors = []
    allow = json.loads((ROOT / "data/allowed_brand_urls.json").read_text(encoding="utf-8"))
    if allow.get("mode") != "exact_source_url_allowlist" or allow.get("allow_discovery") is not False:
        errors.append("ALLOWLIST_CONTRACT_INVALID")
    if allow.get("total_brands") != 120 or len(allow.get("entries", [])) != 440:
        errors.append(f"ALLOWLIST_SCOPE_INVALID:brands={allow.get('total_brands')}:urls={len(allow.get('entries', []))}")
    data = json.loads((ROOT / "data/news.json").read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("items", [])
    for i, item in enumerate(items):
        tracking = str(item.get("affiliate_tracking_url") or "").strip()
        if tracking and not item.get("is_affiliate"):
            errors.append(f"AFFILIATE_TRACKING_WITHOUT_FLAG:{i}")
        if item.get("is_affiliate") and not tracking:
            errors.append(f"AFFILIATE_FLAG_WITHOUT_TRACKING:{i}")
        if tracking and not item.get("affiliate_program_id"):
            errors.append(f"AFFILIATE_TRACKING_WITHOUT_PROGRAM:{i}")
    seo_dir = ROOT / "seo"
    seo_files = sorted(seo_dir.glob("*/index.html")) if seo_dir.exists() else []
    if not seo_files:
        errors.append("NO_SEO_OFFER_PAGES")
    for path in seo_files:
        audit = HTMLAudit()
        audit.feed(path.read_text(encoding="utf-8"))
        if "index" not in audit.robots or "follow" not in audit.robots:
            errors.append(f"SEO_PAGE_NOT_INDEX_FOLLOW:{path}")
        if not audit.canonical.startswith(BASE + "/seo/"):
            errors.append(f"SEO_PAGE_BAD_CANONICAL:{path}")
        if "Last verified:" not in audit.text and "Verification:" not in audit.text:
            errors.append(f"SEO_PAGE_MISSING_VERIFICATION:{path}")
        for href, rel in audit.links:
            if "sponsored" in rel and "affiliate" not in audit.text.lower():
                errors.append(f"SEO_PAGE_SPONSORED_WITHOUT_DISCLOSURE:{path}")
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8") if (ROOT / "sitemap.xml").exists() else ""
    brand_files = sorted((ROOT / "brand").glob("*/index.html")) if (ROOT / "brand").exists() else []
    for path in brand_files:
        audit = HTMLAudit()
        audit.feed(path.read_text(encoding="utf-8"))
        url = audit.canonical
        if "noindex" in audit.robots and url and f"<loc>{url}</loc>" in sitemap:
            errors.append(f"NOINDEX_BRAND_IN_SITEMAP:{path}")
    if errors:
        print("PRE-AFFILIATE VALIDATION FAILED")
        for error in errors[:100]:
            print("-", error)
        raise SystemExit(1)
    print(f"PRE-AFFILIATE VALIDATION PASS: allowlist=120 brands/440 URLs seo_pages={len(seo_files)} affiliate_records=0-or-authorized")

if __name__ == "__main__":
    main()
