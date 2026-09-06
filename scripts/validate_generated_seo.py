import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from bot.seo_offer_articles import VISIBLE_NOISE_RE

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SEO = ROOT / "seo"
SITEMAP = ROOT / "sitemap-seo.xml"
BASE = "https://deal24h.net"


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.canonical = ""
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "link" and attrs.get("rel", "").lower() == "canonical":
            self.canonical = attrs.get("href", "")
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        self.parts.append(data)
        if self.in_title:
            self.title += data

    def text(self):
        return " ".join(self.parts)


def main():
    meta = json.loads((SEO / "seo-modes.json").read_text(encoding="utf-8"))
    expected_total = int(meta["urls"])
    expected_counts = meta["counts"]
    files = sorted(SEO.glob("*/index.html"))
    assert len(files) == expected_total, (len(files), expected_total)

    news = json.loads(DATA.read_text(encoding="utf-8"))
    purchase_urls = {str(x.get("final_purchase_url") or "").strip() for x in news}
    purchase_urls.discard("")

    seen = set()
    counts = {"code": 0, "direct": 0}
    errors = []

    for path in files:
        parser = VisibleText()
        parser.feed(path.read_text(encoding="utf-8"))
        visible = re.sub(r"\s+", " ", parser.text()).strip()
        canonical = parser.canonical.strip()
        expected_canonical = f"{BASE}/{path.parent.relative_to(SEO).as_posix()}/"

        if not canonical or canonical != expected_canonical:
            errors.append(f"BAD_CANONICAL:{path}:{canonical}")
        if canonical in seen:
            errors.append(f"DUPLICATE_CANONICAL:{canonical}")
        seen.add(canonical)
        if VISIBLE_NOISE_RE.search(visible):
            errors.append(f"VISIBLE_NOISE:{path}")

        is_code = "PROMO CODE" in visible and "Copy code" in visible and "GET CODE" in visible
        is_direct = "DIRECT DEAL" in visible and "GET DEAL" in visible and "Copy code" not in visible
        if is_code:
            counts["code"] += 1
        elif is_direct:
            counts["direct"] += 1
        else:
            errors.append(f"BAD_OFFER_MODE:{path}")

        ctas = [u for u in parser.links if u.startswith(("http://", "https://")) and u != BASE + "/"]
        if not any(u in purchase_urls for u in ctas):
            errors.append(f"CTA_NOT_VERIFIED_PURCHASE_URL:{path}")

    assert counts == {"code": int(expected_counts["code"]), "direct": int(expected_counts["direct"])}, counts

    sitemap_urls = set(re.findall(r"<loc>(https://deal24h\.net/seo/[^<]+/)</loc>", SITEMAP.read_text(encoding="utf-8"))) if SITEMAP.exists() else set()
    if sitemap_urls != seen:
        errors.append(f"SITEMAP_MISMATCH:missing={len(seen-sitemap_urls)}:extra={len(sitemap_urls-seen)}")

    if errors:
        print("GENERATED SEO VALIDATION FAILED")
        for error in errors[:100]:
            print("-", error)
        raise SystemExit(1)

    print(f"GENERATED SEO VALIDATION PASS: code={counts['code']} direct={counts['direct']} total={len(files)} visible_text_noise=0 canonical_unique=1 sitemap_match=1")


if __name__ == "__main__":
    main()
