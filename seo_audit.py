from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests

from seo_analysis import analyze_url
from seo_utils import (
    HEADERS,
    REQUEST_TIMEOUT,
    normalize_url_for_comparison,
    site_key,
)


def normalize_url_key(url: str) -> str:
    return "|".join(normalize_url_for_comparison(url))


def is_same_site_url(url_a: str, url_b: str) -> bool:
    return site_key(urlparse(url_a).netloc) == site_key(urlparse(url_b).netloc)


def parse_sitemap_xml(xml_content: bytes | str) -> dict[str, list[str]]:
    if isinstance(xml_content, bytes):
        xml_content = xml_content.decode("utf-8", errors="ignore")

    root = ET.fromstring(xml_content)
    root_tag = root.tag.rsplit("}", 1)[-1].lower()
    parsed: dict[str, list[str]] = {"urls": [], "sitemaps": []}

    if root_tag == "urlset":
        for node in root.findall(".//{*}url/{*}loc"):
            if node.text and node.text.strip():
                parsed["urls"].append(node.text.strip())
    elif root_tag == "sitemapindex":
        for node in root.findall(".//{*}sitemap/{*}loc"):
            if node.text and node.text.strip():
                parsed["sitemaps"].append(node.text.strip())

    return parsed


def discover_sitemap_urls(start_url: str, max_urls: int = 50) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    parsed = urlparse(start_url)
    if not parsed.scheme or not parsed.netloc:
        return [], ["A valid site URL is required for sitemap discovery."]

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    candidates: list[str] = []

    robots_url = urljoin(base_url, "/robots.txt")
    try:
        robots_response = requests.get(robots_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if robots_response.status_code == 200:
            for line in robots_response.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if sitemap_url:
                        candidates.append(sitemap_url)
    except requests.exceptions.RequestException as exc:
        warnings.append(f"Could not read robots.txt for sitemap discovery: {exc}")

    candidates.extend(
        [
            urljoin(base_url, "/sitemap.xml"),
            urljoin(base_url, "/sitemap_index.xml"),
        ]
    )

    seen_sitemaps: set[str] = set()
    collected_urls: list[str] = []
    queue = deque(candidates)

    while queue and len(collected_urls) < max_urls:
        sitemap_url = queue.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            response = requests.get(sitemap_url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if response.status_code != 200:
                continue
            parsed_xml = parse_sitemap_xml(response.content)
            queue.extend(parsed_xml["sitemaps"])
            for page_url in parsed_xml["urls"]:
                if not is_same_site_url(start_url, page_url):
                    continue
                if normalize_url_key(page_url) in {normalize_url_key(item) for item in collected_urls}:
                    continue
                collected_urls.append(page_url)
                if len(collected_urls) >= max_urls:
                    break
        except (requests.exceptions.RequestException, ET.ParseError) as exc:
            warnings.append(f"Skipped sitemap `{sitemap_url}`: {exc}")

    if not collected_urls:
        warnings.append("No crawlable same-site URLs were discovered from sitemap sources.")

    return collected_urls[:max_urls], warnings


def summarize_page_result(result: dict[str, Any], requested_url: str) -> dict[str, Any]:
    if result.get("fetch_error"):
        return {
            "requested_url": requested_url,
            "final_url": result.get("final_url", requested_url),
            "fetch_error": result["fetch_error"],
            "warnings": result.get("warnings", []),
            "overall_score": 0.0,
            "meta_score": 0.0,
            "content_score": 0.0,
            "link_score": 0.0,
            "tech_score": 0.0,
            "page_type": "unknown",
            "issues": [],
            "high_issue_count": 0,
            "medium_issue_count": 0,
            "low_issue_count": 0,
            "indexable": False,
            "title": None,
            "title_status": "missing",
            "description": None,
            "description_status": "missing",
            "canonical": None,
            "canonical_status": "missing",
            "primary_h1": None,
            "h1_count": 0,
            "word_count": 0,
            "internal_links": 0,
            "external_links": 0,
        }

    issues = result.get("issues", [])
    severity_counts = Counter(issue["severity"] for issue in issues)
    content_data = result["content_data"]
    meta_data = result["meta_data"]
    link_data = result["link_data"]

    return {
        "requested_url": requested_url,
        "final_url": result["final_url"],
        "fetch_error": None,
        "warnings": result.get("warnings", []),
        "overall_score": round(result["overall_score"], 1),
        "meta_score": round(result["meta_score"], 1),
        "content_score": round(result["content_score"], 1),
        "link_score": round(result["link_score"], 1),
        "tech_score": round(result["tech_score"], 1),
        "page_type": content_data["page_type"],
        "issues": issues,
        "high_issue_count": severity_counts.get("high", 0),
        "medium_issue_count": severity_counts.get("medium", 0),
        "low_issue_count": severity_counts.get("low", 0),
        "indexable": result["tech_data"]["indexability"]["can_be_indexed"],
        "title": meta_data.get("title"),
        "title_status": meta_data.get("title_status"),
        "description": meta_data.get("description"),
        "description_status": meta_data.get("description_status"),
        "canonical": meta_data.get("canonical"),
        "canonical_status": meta_data.get("canonical_status"),
        "primary_h1": content_data["headings"].get("h1", [None])[0],
        "h1_count": len(content_data["headings"].get("h1", [])),
        "word_count": content_data["word_count"],
        "internal_links": link_data["internal_count"],
        "external_links": link_data["external_count"],
    }


def build_site_audit_summary(pages: list[dict[str, Any]]) -> dict[str, Any]:
    analyzed_pages = [page for page in pages if not page["fetch_error"]]
    issue_totals = Counter()
    issue_by_page_type: dict[str, Counter[str]] = defaultdict(Counter)
    page_type_counts = Counter(page["page_type"] for page in analyzed_pages)

    for page in analyzed_pages:
        for issue in page["issues"]:
            issue_totals[issue["message"]] += 1
            issue_by_page_type[page["page_type"]][issue["message"]] += 1

    def duplicate_groups(values: list[tuple[str | None, str]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for value, url in values:
            normalized = (value or "").strip()
            if normalized:
                grouped[normalized].append(url)
        duplicates = [
            {"value": value, "urls": urls, "count": len(urls)}
            for value, urls in grouped.items()
            if len(urls) > 1
        ]
        duplicates.sort(key=lambda item: (-item["count"], item["value"]))
        return duplicates

    pages_missing = {
        "title": [page["final_url"] for page in analyzed_pages if page["title_status"] == "missing"],
        "description": [page["final_url"] for page in analyzed_pages if page["description_status"] == "missing"],
        "h1": [page["final_url"] for page in analyzed_pages if page["h1_count"] == 0],
        "canonical": [page["final_url"] for page in analyzed_pages if page["canonical_status"] == "missing"],
    }

    return {
        "pages_crawled": len(pages),
        "pages_analyzed": len(analyzed_pages),
        "pages_with_errors": len([page for page in pages if page["fetch_error"]]),
        "average_score": round(
            sum(page["overall_score"] for page in analyzed_pages) / len(analyzed_pages),
            1,
        )
        if analyzed_pages
        else 0.0,
        "indexable_pages": len([page for page in analyzed_pages if page["indexable"]]),
        "non_indexable_pages": len([page for page in analyzed_pages if not page["indexable"]]),
        "page_type_counts": dict(page_type_counts),
        "top_issues": [
            {"message": message, "count": count}
            for message, count in issue_totals.most_common(10)
        ],
        "issues_by_page_type": {
            page_type: [{"message": message, "count": count} for message, count in counter.most_common(5)]
            for page_type, counter in issue_by_page_type.items()
        },
        "missing_by_field": pages_missing,
        "duplicate_titles": duplicate_groups([(page["title"], page["final_url"]) for page in analyzed_pages]),
        "duplicate_descriptions": duplicate_groups(
            [(page["description"], page["final_url"]) for page in analyzed_pages]
        ),
        "duplicate_h1s": duplicate_groups([(page["primary_h1"], page["final_url"]) for page in analyzed_pages]),
        "lowest_scoring_pages": sorted(
            analyzed_pages,
            key=lambda page: (page["overall_score"], page["high_issue_count"], page["medium_issue_count"]),
        )[:10],
    }


def audit_from_url_list(urls: list[str], fetch_mode: str = "auto") -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []

    for url in urls:
        result = analyze_url(url, fetch_mode=fetch_mode)
        pages.append(summarize_page_result(result, url))
        warnings.extend(result.get("warnings", []))

    return {
        "pages": pages,
        "summary": build_site_audit_summary(pages),
        "warnings": warnings,
    }


def crawl_site(start_url: str, max_urls: int = 25, fetch_mode: str = "auto") -> dict[str, Any]:
    queue = deque([start_url])
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []

    while queue and len(pages) < max_urls:
        current_url = queue.popleft()
        current_key = normalize_url_key(current_url)
        if current_key in seen:
            continue
        seen.add(current_key)

        result = analyze_url(current_url, fetch_mode=fetch_mode)
        pages.append(summarize_page_result(result, current_url))
        warnings.extend(result.get("warnings", []))

        if result.get("fetch_error"):
            continue

        for next_url in result["link_data"]["internal"]:
            if not is_same_site_url(start_url, next_url):
                continue
            next_key = normalize_url_key(next_url)
            if next_key in seen:
                continue
            queue.append(next_url)

    return {
        "pages": pages,
        "summary": build_site_audit_summary(pages),
        "warnings": warnings,
    }


def run_site_audit(
    start_url: str,
    discovery_mode: str = "auto",
    max_urls: int = 25,
    fetch_mode: str = "auto",
) -> dict[str, Any]:
    selected_discovery_mode = (discovery_mode or "auto").lower()
    if selected_discovery_mode not in {"auto", "sitemap", "crawl"}:
        raise ValueError("discovery_mode must be one of: auto, sitemap, crawl")

    report: dict[str, Any] = {
        "target": start_url,
        "discovery_mode": selected_discovery_mode,
        "fetch_mode": fetch_mode,
        "warnings": [],
        "pages": [],
        "summary": build_site_audit_summary([]),
        "source": "crawl",
    }

    if selected_discovery_mode in {"auto", "sitemap"}:
        sitemap_urls, sitemap_warnings = discover_sitemap_urls(start_url, max_urls=max_urls)
        report["warnings"].extend(sitemap_warnings)
        if sitemap_urls:
            audit_report = audit_from_url_list(sitemap_urls[:max_urls], fetch_mode=fetch_mode)
            report.update(audit_report)
            report["source"] = "sitemap"
            return report
        if selected_discovery_mode == "sitemap":
            return report

    crawl_report = crawl_site(start_url, max_urls=max_urls, fetch_mode=fetch_mode)
    report.update(crawl_report)
    report["source"] = "crawl"
    return report
