import json
import re
from html.parser import HTMLParser
from pathlib import Path

from bot.seo_offer_articles import VISIBLE_NOISE_RE, make_article

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SEO = ROOT / "seo"
SITEMAP = ROOT / "sitemap-seo.xml"
BASE = "https://deal24h.net"


class VisibleText(HTMLParser):
    """Collect rendered text/links while ignoring non-visible HTML blocks."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.canonical = ""
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in {"script", "style", "template", "noscript"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
            self.canonical = attrs.get("href", "")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "template", "noscript"}:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)

    def text(self):
        return " ".join(self.parts)


def main():
    meta = json.loads((SEO / "seo-modes.json").read_text(encoding="utf-8"))
    expected_total = int(meta["urls"])
    expected_counts = {"code": int(meta["counts"]["code"]), "direct": int(meta["counts"]["direct"])}
    files = sorted(SEO.glob("*/index.html"))
    assert len(files) == expected_total, (len(files), expected_total)

    news = json.loads(DATA.read_text(encoding="utf-8"))
    expected_by_canonical = {}
    for item in news:
        result = make_article(item)
        if not result:
            continue
        canonical, _html, label = result
        expected_by_canonical[canonical] = {
            "purchase": str(item.get("final_purchase_url") or "").strip(),
            "label": label,
        }

    seen = set()
    counts = {"code": 0, "direct": 0}
    errors = []

    for path in files:
        parser = VisibleText()
        parser.feed(path.read_text(encoding="utf-8"))
        visible = re.sub(r"\s+", " ", parser.text()).strip()
        canonical = parser.canonical.strip()
        expected_canonical = f"{BASE}/{path.parent.relative_to(SEO).as_posix()}/"

        if canonical != expected_canonical:
            errors.append(f"BAD_CANONICAL:{path}:{canonical}")
        if canonical in seen:
            errors.append(f"DUPLICATE_CANONICAL:{canonical}")
        seen.add(canonical)
        if VISIBLE_NOISE_RE.search(visible):
            errors.append(f"VISIBLE_NOISE:{path}")

        expected = expected_by_canonical.get(canonical)
        if not expected:
            errors.append(f"CANONICAL_NOT_IN_VERIFIED_OFFERS:{path}:{canonical}")
        else:
            is_code = "PROMO CODE" in visible and "Copy code" in visible and "GET CODE" in visible
            is_direct = "DIRECT DEAL" in visible and "GET DEAL" in visible and "Copy code" not in visible
            if is_code:
                counts["code"] += 1
            elif is_direct:
                counts["direct"] += 1
            else:
                errors.append(f"BAD_OFFER_MODE:{path}")

            if expected["label"] == "Promo code" and not is_code:
                errors.append(f"EXPECTED_CODE_MODE:{path}")
            if expected["label"] == "Direct deal" and not is_direct:
                errors.append(f"EXPECTED_DIRECT_MODE:{path}")

            exact_purchase = expected["purchase"]
            if not exact_purchase or exact_purchase not in parser.links:
                errors.append(f"CTA_NOT_EXACT_PURCHASE_URL:{path}:{exact_purchase}")

    if counts != expected_counts:
        errors.append(f"MODE_COUNTS_MISMATCH:expected={expected_counts}:actual={counts}")

    sitemap_urls = set(re.findall(r"<loc>(https://deal24h\.net/seo/[^<]+/)</loc>", SITEMAP.read_text(encoding="utf-8"))) if SITEMAP.exists() else set()
    if sitemap_urls != seen:
        errors.append(f"SITEMAP_MISMATCH:missing={len(seen-sitemap_urls)}:extra={len(sitemap_urls-seen)}")

    if errors:
        print("GENERATED SEO VALIDATION FAILED")
        for error in errors[:100]:
            print("-", error)
        raise SystemExit(1)

    print(f"GENERATED SEO VALIDATION PASS: code={counts['code']} direct={counts['direct']} total={len(files)} visible_text_noise=0 canonical_unique=1 exact_cta=1 sitemap_match=1")


if __name__ == "__main__":
    main()
