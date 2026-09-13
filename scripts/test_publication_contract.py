"""Network-free guard for the single-publisher, single-release UI contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CANONICAL = WORKFLOWS / "verified-deal-pipeline.yml"
ANALYTICS = WORKFLOWS / "analytics.yml"

workflow_text = {path.name: path.read_text(encoding="utf-8") for path in WORKFLOWS.glob("*.yml")}
pages_publishers = [
    name
    for name, text in workflow_text.items()
    if "actions/deploy-pages" in text or "actions/upload-pages-artifact" in text
]
assert pages_publishers == [CANONICAL.name], f"Only the verified pipeline may publish Pages: {pages_publishers}"

analytics = ANALYTICS.read_text(encoding="utf-8")
assert "pages: write" not in analytics
assert "actions/deploy-pages" not in analytics
assert "actions/upload-pages-artifact" not in analytics
assert "actions/upload-artifact" in analytics

pipeline = CANONICAL.read_text(encoding="utf-8")
ordered_steps = [
    "python scripts/build_data_shards.py",
    "python bot/seo_offer_articles.py",
    "python bot/seo_generator_999.py",
    "python scripts/stamp_static_release.py",
    "python scripts/validate_generated_seo.py",
    "python scripts/validate_pre_affiliate.py",
    "python scripts/validate_release_consistency.py",
    "python bot/validate_site_fast.py",
    "python scripts/sync_supabase.py",
    "actions/upload-pages-artifact",
    "actions/deploy-pages",
]
positions = [pipeline.index(step) for step in ordered_steps]
assert positions == sorted(positions), "Release build, validation, Supabase sync and Pages deploy order changed"

frontend = (ROOT / "assets" / "app-home.js").read_text(encoding="utf-8")
for required in ("data-manifest.json", "cache:'no-store'", "releaseURL", "assertRelease", "reloadForRelease"):
    assert required in frontend, f"Frontend release guard missing: {required}"
assert "loadFallbackOffers" not in frontend, "Unversioned news.json fallback must not return"

shards = (ROOT / "scripts" / "build_data_shards.py").read_text(encoding="utf-8")
for required in ("release_id_for_rows", "'release_id':release_id", "'items':rows"):
    assert required in shards, f"Versioned shard contract missing: {required}"

generator = (ROOT / "bot" / "seo_generator_999.py").read_text(encoding="utf-8")
assert 'class="seo-offer-card"' in generator
assert '<ul class="seo-offer-list">' not in generator
assert 'name="deal24h-release"' in generator

article_generator = (ROOT / "bot" / "seo_offer_articles.py").read_text(encoding="utf-8")
assert 'name="deal24h-release"' in article_generator
assert "deal24h-release:{release_id}" in article_generator

css = (ROOT / "assets" / "style.css").read_text(encoding="utf-8")
for required in ("div.seo-offer-list", ".seo-offer-card", "grid-template-columns:repeat(2", "grid-template-columns:1fr"):
    assert required in css, f"SEO card CSS contract missing: {required}"

print("PUBLICATION CONTRACT PASS: one Pages publisher, release-locked data, no stale fallback, permanent SEO title cards")
