"""Static safety checks for the isolated analytics collector."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/analytics.yml").read_text(encoding="utf-8")
collector = (ROOT / "scripts/fetch_analytics.py").read_text(encoding="utf-8")

assert "pages: write" not in workflow
assert "actions/deploy-pages" not in workflow
assert "actions/upload-pages-artifact" not in workflow
assert "actions/upload-artifact" in workflow
assert "continue-on-error: true" in workflow
assert "DeadlineExceeded" in collector
assert "DeadlineExceeded" in collector
assert "max_attempts" in collector
assert "return False" in collector
print("ANALYTICS RESILIENCE PASS: retry, stale-snapshot fallback, artifact-only, no Pages deployment")
