"""Network-free guards for promotion title/content quality."""
from bot.catalog_utils import has_indexable_content, repair_text

BASE = {
    "category": "Fashion", "merchant": "Dunelm", "offer_qualified": True,
    "official_source": True,
    "source_verification_status": "assistant_verified_first_party",
    "purchase_url_verification_status": "live_verified",
    "published_offer_authority": "assistant_verified_source_plus_live_brand_purchase_destination",
    "source_url": "https://dunelm.com/sale", "promotion_url": "https://dunelm.com/sale",
    "final_purchase_url": "https://dunelm.com/sale", "url": "https://dunelm.com/sale",
    "status": "active",
}

def check(title, content, expected):
    item = dict(BASE, title=title, content=content)
    assert has_indexable_content(item) is expected, title

check("11.A The Promoter cannot guarantee continuous access", "The Promoter cannot guarantee continuous, uninterrupted or secure access.", False)
check("Food containers pack of 4 £2.50", "Food containers pack of 4 £2.50.", False)
check("Save 20% on selected items", "Save 20% on selected items with code SAVE20.", True)
assert repair_text("cafÃ©") == "café"
print("CONTENT QUALITY CONTRACT PASS")
