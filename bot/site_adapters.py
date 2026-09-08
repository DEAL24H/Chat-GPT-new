"""DEAL24H per-site acquisition adapters.

Requests remains the fast path. Playwright is the browser-rendering fallback for
JavaScript-heavy pages, anti-bot responses, or pages that return an app shell.
The registry is data-driven so a verified per-site API/browser strategy can be
added without changing deal extraction logic.
"""
from __future__ import annotations

import atexit
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "data" / "assistant_verified_source_selection.json"

_JS_SHELL = re.compile(
    r"(?:__next|__nuxt|webpack|vite|react|angular|svelte|application/ld\+json|id=[\"'](?:app|root)[\"'])",
    re.I,
)


@dataclass
class AdapterResponse:
    url: str
    text: str
    status_code: int
    headers: dict[str, str]
    source: str


class AdapterRegistry:
    """Registry built from the canonical 120 verified first-party sources.

    Each website gets an explicit acquisition policy. Actual third-party or
    undocumented APIs are never guessed: api is None until a first-party
    endpoint is separately verified and added to this registry.
    """
    def __init__(self, path: Path = SELECTION):
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = data.get("sources", [])
        if data.get("total") != 120 or len(sources) != 120:
            raise RuntimeError("ADAPTER REGISTRY CONTRACT FAILED: expected 120 verified sources")
        self._sites = {}
        for source in sources:
            domain = self._domain(source.get("official_homepage") or source.get("domain") or "")
            if not domain:
                continue
            self._sites[domain] = {
                "merchant": source.get("merchant") or source.get("name"),
                "category": source.get("category"),
                "official_homepage": source.get("official_homepage"),
                "acquisition": "requests_then_playwright",
                "render_mode": "auto",
                "browser_fallback": True,
                "browser_fallback_min_visible_chars": 700,
                "api": None,
            }
        if len(self._sites) < 118:
            raise RuntimeError(f"ADAPTER REGISTRY CONTRACT FAILED: only {len(self._sites)} unique domains")

    @staticmethod
    def _domain(url: str) -> str:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")

    def for_url(self, url: str) -> dict:
        domain = self._domain(url)
        exact = self._sites.get(domain)
        if exact:
            return exact
        for key, config in self._sites.items():
            if domain.endswith("." + key):
                return config
        return {"acquisition": "requests_then_playwright", "render_mode": "auto", "browser_fallback": True, "browser_fallback_min_visible_chars": 700, "api": None}


class BrowserRenderer:
    """One Chromium instance per worker thread, reused across pages."""

    _local = threading.local()
    _instances: list[object] = []
    _lock = threading.Lock()

    @classmethod
    def _browser(cls):
        state = getattr(cls._local, "state", None)
        if state:
            return state[1]
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        state = (pw, browser)
        cls._local.state = state
        with cls._lock:
            cls._instances.append(state)
        return browser

    @classmethod
    def fetch(cls, url: str, timeout_ms: int, headers: dict[str, str]) -> AdapterResponse:
        browser = cls._browser()
        page = browser.new_page(extra_http_headers=headers)
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
            except Exception:
                pass
            text = page.content()
            final_url = page.url
            status = response.status if response else 200
            return AdapterResponse(
                url=final_url,
                text=text,
                status_code=status,
                headers={"content-type": "text/html"},
                source="playwright",
            )
        finally:
            page.close()


@atexit.register
def _close_browsers() -> None:
    with BrowserRenderer._lock:
        instances = list(BrowserRenderer._instances)
        BrowserRenderer._instances.clear()
    for pw, browser in instances:
        try:
            browser.close()
        finally:
            pw.stop()


class SiteAdapterClient:
    def __init__(self, timeout: int = 15, retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self.registry = AdapterRegistry()

    @staticmethod
    def _same_domain(url: str, domain: str) -> bool:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        domain = domain.lower().removeprefix("www.")
        return bool(host and domain and (host == domain or host.endswith("." + domain)))

    @staticmethod
    def _needs_browser(response: requests.Response, body: str, config: dict) -> bool:
        if config.get("render_mode") == "browser":
            return True
        if config.get("render_mode") == "requests":
            return False
        if response.status_code in {403, 408, 425, 429} or response.status_code >= 500:
            return True
        visible = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", body, flags=re.I | re.S)
        visible = re.sub(r"\s+", " ", visible).strip()
        return len(visible) < int(config.get("browser_fallback_min_visible_chars", 700)) and bool(_JS_SHELL.search(body))

    def fetch(self, url: str, domain: str, headers: dict[str, str]) -> tuple[AdapterResponse | None, str]:
        config = self.registry.for_url(url)
        last = "FETCH_FAILED"
        for attempt in range(self.retries):
            try:
                response = requests.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
                last = f"HTTP_{response.status_code}"
                if response.status_code < 400 and self._same_domain(response.url, domain) and "html" in response.headers.get("content-type", "").lower():
                    body = response.text
                    if self._needs_browser(response, body, config) and config.get("browser_fallback", True):
                        try:
                            browser_response = BrowserRenderer.fetch(response.url, self.timeout * 1000, headers)
                            if self._same_domain(browser_response.url, domain):
                                return browser_response, ""
                        except Exception as exc:
                            last = f"PLAYWRIGHT_{type(exc).__name__}"
                    return AdapterResponse(response.url, body, response.status_code, dict(response.headers), "requests"), ""
                if config.get("browser_fallback", True):
                    try:
                        browser_response = BrowserRenderer.fetch(response.url, self.timeout * 1000, headers)
                        if browser_response.status_code < 400 and self._same_domain(browser_response.url, domain):
                            return browser_response, ""
                    except Exception as exc:
                        last = f"PLAYWRIGHT_{type(exc).__name__}"
                if attempt + 1 < self.retries:
                    continue
                return None, last
            except requests.RequestException as exc:
                last = type(exc).__name__
                if attempt + 1 < self.retries:
                    continue
        return None, last
