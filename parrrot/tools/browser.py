"""
Parrrot — Browser automation via Playwright (opens real Firefox/Chrome)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import asyncio
from typing import Optional

try:
    from playwright.async_api import async_playwright, Browser, Page
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

from parrrot.tools.registry import registry

_INSTALL_MSG = (
    "Browser tools require Playwright. Install with:\n"
    "  pip install playwright\n"
    "  playwright install"
)

# Shared browser state (lazy-initialized)
_browser: "Browser | None" = None
_page: "Page | None" = None
_playwright_ctx = None


async def _get_page() -> "Page":
    global _browser, _page, _playwright_ctx
    if not _HAS_PLAYWRIGHT:
        raise RuntimeError(_INSTALL_MSG)
    if _page is None or _page.is_closed():
        _playwright_ctx = await async_playwright().start()
        _browser = await _playwright_ctx.chromium.launch(headless=False)
        _page = await _browser.new_page()
    return _page


async def _web_search(query: str, engine: str = "duckduckgo") -> str:
    """Open browser, search, return page text summary."""
    try:
        page = await _get_page()
        if engine == "duckduckgo":
            url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
        else:
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1)

        # Try to extract search result snippets
        text = await page.evaluate("""() => {
            const results = [];
            // DuckDuckGo result elements
            document.querySelectorAll('[data-result="snippet"], .result__snippet, .kc_zmnd_fQ, h2, p').forEach(el => {
                const t = el.innerText.trim();
                if (t.length > 30 && t.length < 500) results.push(t);
            });
            return results.slice(0, 10).join('\\n\\n');
        }""")

        if not text:
            # Fallback: get all body text
            text = await page.inner_text("body")
            text = text[:3000]

        return f"Search results for '{query}':\n\n{text[:2000]}"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Browser search failed: {e}. Make sure a browser is available."


async def _open_url(url: str) -> str:
    try:
        page = await _get_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = await page.title()
        return f"Opened: {title} ({url})"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Could not open URL: {e}"


async def _get_page_text(url: str, max_chars: int = 5000) -> str:
    try:
        page = await _get_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        text = await page.inner_text("body")
        return text[:max_chars]
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Could not read page: {e}"


async def _read_current_page() -> str:
    try:
        page = await _get_page()
        title = await page.title()
        text = await page.inner_text("body")
        return f"Page: {title}\n\n{text[:4000]}"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"No page open or error: {e}"


async def _click_element(description: str) -> str:
    """Click a button or link by its visible text."""
    try:
        page = await _get_page()
        # Try to find by text
        locator = page.get_by_text(description, exact=False).first
        await locator.click(timeout=5000)
        return f"Clicked: '{description}'"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Could not click '{description}': {e}"


async def _fill_form(field_description: str, value: str) -> str:
    """Fill a form field identified by its label or placeholder text."""
    try:
        page = await _get_page()
        # Try label match
        try:
            await page.get_by_label(field_description, exact=False).fill(value, timeout=3000)
            return f"Filled '{field_description}' with '{value}'"
        except Exception:
            pass
        # Try placeholder
        await page.get_by_placeholder(field_description, exact=False).fill(value, timeout=3000)
        return f"Filled '{field_description}' with '{value}'"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Could not fill '{field_description}': {e}"


async def _take_page_screenshot() -> str:
    """Take a screenshot of the current browser page. Returns file path."""
    try:
        import tempfile
        page = await _get_page()
        path = tempfile.mktemp(suffix=".png")
        await page.screenshot(path=path, full_page=False)
        return f"Screenshot saved: {path}"
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Screenshot failed: {e}"


async def _download_file(url: str, destination: str) -> str:
    """Download a file from a URL."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            import os
            dest = os.path.expanduser(destination)
            with open(dest, "wb") as f:
                f.write(r.content)
            return f"Downloaded {len(r.content):,} bytes to {dest}"
    except Exception as e:
        return f"Download failed: {e}"


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

registry.register(
    "web_search",
    "Open browser, search the web, return results summary",
    {"query": "search query", "engine": "search engine: 'duckduckgo' (default) or 'google'"},
)(_web_search)

registry.register(
    "open_url",
    "Open a URL in the browser",
    {"url": "URL to open"},
)(_open_url)

registry.register(
    "get_page_text",
    "Navigate to a URL and extract all text content",
    {"url": "URL to visit", "max_chars": "maximum chars to return (default 5000)"},
)(_get_page_text)

registry.register(
    "read_current_page",
    "Read the text of the currently open browser page",
    {},
)(_read_current_page)

registry.register(
    "click_element",
    "Click a button or link on the current page by its visible text",
    {"description": "visible text or label of the element to click"},
)(_click_element)

registry.register(
    "fill_form",
    "Fill a form field on the current page",
    {"field_description": "label or placeholder of the field", "value": "value to type"},
)(_fill_form)

registry.register(
    "take_page_screenshot",
    "Take a screenshot of the current browser page",
    {},
)(_take_page_screenshot)

registry.register(
    "download_file",
    "Download a file from a URL to local disk",
    {"url": "file URL", "destination": "local file path"},
)(_download_file)
