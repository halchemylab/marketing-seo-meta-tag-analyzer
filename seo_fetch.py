import re
import time
from html import unescape
from typing import Any

import requests  # type: ignore[import-untyped]

from seo_utils import (
    HEADERS,
    RENDER_NETWORK_IDLE_TIMEOUT_MS,
    RENDER_SETTLE_DELAY_MS,
    RENDER_WAIT_TIMEOUT_MS,
    REQUEST_TIMEOUT,
    parse_html,
    tokenize_text,
)

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - exercised via integration behavior
    PlaywrightTimeoutError = None
    sync_playwright = None


def fetch_content(url: str) -> tuple[bytes | None, str, float | None, str | None, list[str], dict[str, Any]]:
    return fetch_content_static(url)


def fetch_content_static(
    url: str,
) -> tuple[bytes | None, str, float | None, str | None, list[str], dict[str, Any]]:
    warnings: list[str] = []
    try:
        start_time = time.time()
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        end_time = time.time()
        load_time = end_time - start_time
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            warnings.append(
                f"Content type is '{content_type}', not 'text/html'. Analysis might be limited."
            )
        return response.content, response.url, load_time, None, warnings, dict(response.headers)
    except requests.exceptions.Timeout:
        return None, url, None, f"Error: Request timed out after {REQUEST_TIMEOUT} seconds.", warnings, {}
    except requests.exceptions.RequestException as exc:
        return None, url, None, f"Error fetching URL: {exc}", warnings, {}
    except Exception as exc:
        return None, url, None, f"An unexpected error occurred during fetch: {exc}", warnings, {}


def can_use_rendered_fetch() -> bool:
    return sync_playwright is not None and PlaywrightTimeoutError is not None


def extract_title_from_html(html_content: str | bytes | None) -> str:
    if not html_content:
        return ""
    if isinstance(html_content, bytes):
        html_content = html_content.decode("utf-8", errors="ignore")
    match = re.search(r"<title[^>]*>(.*?)</title>", html_content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return unescape(re.sub(r"\s+", " ", match.group(1))).strip()


def should_attempt_rendered_fetch(html_content: str | bytes | None) -> bool:
    if not html_content:
        return False

    soup = parse_html(html_content)
    raw_text = soup.get_text(" ", strip=True)
    visible_word_count = len(tokenize_text(raw_text))
    script_count = len(soup.find_all("script"))
    heading_count = len(soup.find_all(["h1", "h2", "h3"]))
    title = extract_title_from_html(html_content)
    meta_description = soup.find("meta", attrs={"name": "description"})
    body = soup.find("body") or soup

    app_shell_selectors = [
        {"id": re.compile(r"^(app|root|__next|__nuxt)$", re.I)},
        {"data-reactroot": True},
        {"ng-version": True},
    ]
    has_app_shell_marker = any(body.find(attrs=dict(selector)) for selector in app_shell_selectors)

    scripted_shell_text = body.get_text(" ", strip=True).lower()
    shell_phrases = {
        "enable javascript",
        "loading...",
        "please wait",
        "app loading",
    }
    has_shell_phrase = any(phrase in scripted_shell_text for phrase in shell_phrases)

    sparse_shell = visible_word_count < 120 and script_count >= 8 and heading_count == 0
    weak_metadata = not title and meta_description is None and script_count >= 10
    return has_app_shell_marker or has_shell_phrase or sparse_shell or weak_metadata


def fetch_content_rendered(
    url: str,
) -> tuple[bytes | None, str, float | None, str | None, list[str], dict[str, Any]]:
    warnings: list[str] = []
    if not can_use_rendered_fetch():
        return (
            None,
            url,
            None,
            "Rendered analysis requires Playwright. Install `playwright` and run `playwright install chromium`.",
            warnings,
            {},
        )

    browser = None
    try:
        start_time = time.time()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1440, "height": 900},
                ignore_https_errors=True,
            )
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=RENDER_WAIT_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=RENDER_NETWORK_IDLE_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                warnings.append(
                    "Rendered analysis did not reach network idle before timeout; using the best available DOM snapshot."
                )
            page.wait_for_timeout(RENDER_SETTLE_DELAY_MS)
            html_content = page.content().encode("utf-8")
            final_url = page.url
            load_time = time.time() - start_time
            response_headers = dict(response.headers) if response else {}
            content_type = response_headers.get("content-type", "").lower()
            if content_type and "text/html" not in content_type:
                warnings.append(
                    f"Rendered response content type is '{content_type}', not 'text/html'. Analysis might be limited."
                )
            context.close()
            browser.close()
            browser = None
            return html_content, final_url, load_time, None, warnings, response_headers
    except PlaywrightTimeoutError:
        return (
            None,
            url,
            None,
            f"Rendered analysis timed out after {RENDER_WAIT_TIMEOUT_MS / 1000:.0f} seconds.",
            warnings,
            {},
        )
    except Exception as exc:
        return None, url, None, f"Error during rendered analysis: {exc}", warnings, {}
    finally:
        if browser is not None:
            browser.close()
