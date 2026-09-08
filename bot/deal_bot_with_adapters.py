"""Run the canonical deal bot with the per-site acquisition adapter layer."""
from bot import deal_bot
from bot.site_adapters import SiteAdapterClient

_adapter = SiteAdapterClient(timeout=deal_bot.TIMEOUT, retries=deal_bot.RETRIES)
deal_bot.fetch = lambda url, domain: _adapter.fetch(url, domain, deal_bot.H)


def main() -> None:
    deal_bot.main()


if __name__ == "__main__":
    main()
