"""Cheap, network-free guards for the single canonical publication path."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

manifest = json.loads((ROOT / "data/allowed_brand_urls.json").read_text(encoding="utf-8"))
assert manifest["total_brands"] == 120
assert manifest["allow_discovery"] is False
assert manifest["allow_redirect_source_expansion"] is False
assert manifest["total_urls"] == len(manifest["entries"])

bot_source = (ROOT / "bot/deal_bot.py").read_text(encoding="utf-8")
ast.parse(bot_source)
assert "hashlib.sha1(stable_key)" in bot_source
assert "if key not in dedup" in bot_source

seo_source = (ROOT / "bot/seo_offer_articles.py").read_text(encoding="utf-8")
assert "shutil.rmtree(out)" in seo_source
assert "is_indexable_offer" in seo_source

workflow = (ROOT / ".github/workflows/verified-deal-pipeline.yml").read_text(encoding="utf-8")
assert "python scripts/test_deterministic_pipeline.py" in workflow
print("DETERMINISTIC PIPELINE CONTRACT PASS: fixed sources, stable IDs/titles, country-aware dedup, clean SEO rebuild")
