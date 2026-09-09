"""Run the exact Excel URL allowlist crawler with browser-rendering fallback.

The source boundary is enforced by deal_bot.load_sources(). This wrapper only
installs the requests -> Playwright acquisition adapter; it never discovers or
adds source URLs.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot import deal_bot
from bot.site_adapters import SiteAdapterClient

_adapter = SiteAdapterClient(timeout=deal_bot.TIMEOUT, retries=deal_bot.RETRIES)
deal_bot.fetch = lambda url, domain: _adapter.fetch(url, domain, deal_bot.H)


def main() -> None:
    deal_bot.main()


if __name__ == "__main__":
    main()
