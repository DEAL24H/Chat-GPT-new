import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bot" / "seo_offer_articles.py"
spec = importlib.util.spec_from_file_location("seo_offer_articles", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# This fixture intentionally satisfies the canonical published-offer contract.
def offer(**overrides):
    item = {
        "merchant": "Zara",
        "category": "Fashion",
        "title": "Summer sale 20% off selected items",
        "content": "Summer sale: save 20% off selected items. Add to cart Checkout Current price.",
        "discount": "20% off",
        "code": "SAVE20",
        "promotion_type": "coupon_code",
        "promotion_url": "https://zara.com/offers/summer",
        "source_url": "https://zara.com/offers/summer",
        "official_homepage": "https://zara.com/",
        "final_purchase_url": "https://zara.com/products/example",
        "url": "https://zara.com/products/example",
        "offer_qualified": True,
        "official_source": True,
        "source_verification_status": "assistant_verified_first_party",
        "purchase_url_verification_status": "live_verified",
        "published_offer_authority": "assistant_verified_source_plus_live_brand_purchase_destination",
        "status": "active",
    }
    item.update(overrides)
    return item


# Noise must disappear from every field that becomes visible, including a
# discount value copied from a scraped page.
item = offer()
canonical, html_text, label = mod.make_article(item)
assert canonical and label == "Promo code"
assert not mod.VISIBLE_NOISE_RE.search(html_text)
assert "SAVE20" in html_text
assert "https://zara.com/products/example" in html_text

# Direct promotions must remain supported and must not display a code.
direct = offer(
    title="Free shipping on orders over $50",
    content="Free shipping on orders over $50. Add to cart and checkout are interface text.",
    discount="Free shipping",
    code="",
    promotion_type="direct_promotion",
)
canonical2, html_text2, label2 = mod.make_article(direct)
assert canonical2 and canonical2 != canonical
assert label2 == "Direct deal"
assert "CODE" not in html_text2
assert not mod.VISIBLE_NOISE_RE.search(html_text2)

# Two otherwise identical offers from different promotion pages must not
# collapse to the same canonical URL.
third = offer(promotion_url="https://zara.com/offers/summer-2", source_url="https://zara.com/offers/summer-2")
canonical3, _, _ = mod.make_article(third)
assert canonical3 not in {canonical, canonical2}

print("SEO GENERATOR PREFLIGHT PASS: canonical published contract, code/direct, noise sanitization, CTA destination, and canonical uniqueness")
