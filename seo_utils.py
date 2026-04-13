import re
from collections import Counter
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from seo_models import IssueDict

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = 15
RENDER_WAIT_TIMEOUT_MS = 15000
RENDER_NETWORK_IDLE_TIMEOUT_MS = 5000
RENDER_SETTLE_DELAY_MS = 750
MIN_CONTENT_LENGTH_WORDS = 300
GOOD_LOAD_TIME_THRESHOLD = 2.0
OK_LOAD_TIME_THRESHOLD = 4.0
GOOD_READABILITY_THRESHOLD = 60
MAX_KEYWORDS_TO_SHOW = 10
TITLE_MIN_LENGTH = 15
TITLE_MAX_LENGTH = 60
DESCRIPTION_MIN_LENGTH = 70
DESCRIPTION_MAX_LENGTH = 160
PAGE_TYPE_CONTENT_THRESHOLDS = {
    "homepage": 60,
    "product": 60,
    "category": 80,
    "article": 300,
    "documentation": 180,
    "generic": 150,
}


def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def parse_html(html_content: str | bytes) -> BeautifulSoup:
    try:
        return BeautifulSoup(html_content, "lxml")
    except Exception:
        return BeautifulSoup(html_content, "html.parser")


def get_domain(url: str) -> str | None:
    try:
        return urlparse(url).netloc
    except Exception:
        return None


def normalize_netloc(netloc: str | None) -> str:
    if not netloc:
        return ""
    return netloc.lower().split(":")[0].removeprefix("www.")


def site_key(netloc: str | None) -> str:
    normalized = normalize_netloc(netloc)
    parts = normalized.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return normalized


def is_same_site(url_a: str, url_b: str) -> bool:
    return site_key(get_domain(url_a)) == site_key(get_domain(url_b))


def validate_length(text: str | None, min_length: int, max_length: int) -> str:
    if not text:
        return "missing"
    text_length = len(text.strip())
    if min_length <= text_length <= max_length:
        return "good"
    if text_length < min_length:
        return "short"
    return "long"


def validate_canonical_url(page_url: str, canonical_url: str | None) -> str:
    if not canonical_url:
        return "missing"
    parsed = urlparse(canonical_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid"
    if parsed.fragment:
        return "invalid"
    if not is_same_site(page_url, canonical_url):
        return "cross_domain"
    return "good"


def normalize_url_for_comparison(url: str) -> tuple[str, str, str, str]:
    parsed = urlparse(url)
    normalized_path = parsed.path or "/"
    if normalized_path != "/" and normalized_path.endswith("/"):
        normalized_path = normalized_path.rstrip("/")
    return (
        parsed.scheme.lower(),
        normalize_netloc(parsed.netloc),
        normalized_path,
        parsed.query,
    )


def parse_robots_directives(content: str | None) -> set[str]:
    if not content:
        return set()
    return {directive.strip().lower() for directive in content.split(",") if directive.strip()}


def parse_x_robots_tag(headers: dict[str, Any]) -> list[str]:
    if not headers:
        return []

    raw_values = []
    if hasattr(headers, "get_all"):
        raw_values.extend(headers.get_all("X-Robots-Tag", []))

    header_value = headers.get("X-Robots-Tag")
    if header_value:
        raw_values.append(header_value)

    directives = set()
    for raw_value in raw_values:
        for part in raw_value.split(","):
            directive = part.strip().lower()
            if not directive:
                continue
            if ":" in directive:
                _, directive = directive.split(":", 1)
                directive = directive.strip()
            if directive:
                directives.add(directive)
    return sorted(directives)


def validate_viewport_content(content: str | None) -> str:
    if not content:
        return "missing"
    normalized = content.replace(" ", "").lower()
    if "width=device-width" not in normalized:
        return "invalid"
    if "initial-scale=1" in normalized:
        return "good"
    return "partial"


def extract_schema_types(schema_json: Any) -> list[str]:
    schema_types = []
    if isinstance(schema_json, dict):
        if "@graph" in schema_json and isinstance(schema_json["@graph"], list):
            for item in schema_json["@graph"]:
                schema_types.extend(extract_schema_types(item))
        schema_type = schema_json.get("@type")
        if isinstance(schema_type, list):
            schema_types.extend(str(item) for item in schema_type)
        elif schema_type:
            schema_types.append(str(schema_type))
    elif isinstance(schema_json, list):
        for item in schema_json:
            schema_types.extend(extract_schema_types(item))
    return schema_types


def build_issue(
    category: str,
    severity: str,
    message: str,
    evidence: dict[str, Any] | None = None,
    recommendation: str | None = None,
) -> IssueDict:
    return {
        "category": category,
        "severity": severity,
        "message": message,
        "evidence": evidence or {},
        "recommendation": recommendation,
    }


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_text(text: str | None) -> list[str]:
    if not text:
        return []
    return [token for token in clean_text(text).split() if len(token) > 2]


def detect_page_type(soup: BeautifulSoup, page_url: str) -> str:
    path = (urlparse(page_url).path or "/").lower()
    path_segments = [segment for segment in path.split("/") if segment]
    body = soup.find("body") or soup

    if path == "/" or body.find("main") and len(path_segments) == 0:
        return "homepage"
    if body.find("article") or soup.find("meta", attrs={"property": "article:published_time"}):
        return "article"
    if body.find(attrs={"itemtype": re.compile("product", re.I)}) or re.search(
        r"(add to cart|buy now|\$\d|usd|price)",
        body.get_text(" ", strip=True),
        re.I,
    ):
        return "product"
    if any(segment in {"docs", "documentation", "guide", "api"} for segment in path_segments) or body.find_all(["pre", "code"]):
        return "documentation"
    if any(segment in {"category", "collections", "shop", "products"} for segment in path_segments):
        return "category"
    if len(body.find_all("a", href=True)) >= 20 and len(body.find_all(["h2", "h3"])) >= 3:
        return "category"
    return "generic"


def get_primary_content_root(soup: BeautifulSoup) -> tuple[Any, str | None]:
    primary_selectors = [
        ("main", {}),
        ("article", {}),
        ("div", {"role": "main"}),
        ("section", {"role": "main"}),
    ]
    for tag_name, attrs in primary_selectors:
        root = soup.find(tag_name, attrs=attrs)
        if root:
            return deepcopy(root), tag_name

    body = soup.find("body")
    if body:
        return deepcopy(body), "body"
    return None, None


def count_content_words(text: str | None) -> int:
    return len([word for word in (text or "").split() if word])


def assess_title_h1_alignment(title: str | None, h1_text: str | None) -> dict[str, Any]:
    if not title or not h1_text:
        return {"status": "missing", "overlap_ratio": 0.0, "shared_terms": []}
    title_terms = set(tokenize_text(title))
    h1_terms = set(tokenize_text(h1_text))
    if not title_terms or not h1_terms:
        return {"status": "missing", "overlap_ratio": 0.0, "shared_terms": []}

    shared_terms = sorted(title_terms & h1_terms)
    overlap_ratio = len(shared_terms) / max(min(len(title_terms), len(h1_terms)), 1)
    if overlap_ratio >= 0.5:
        status = "good"
    elif overlap_ratio >= 0.2:
        status = "partial"
    else:
        status = "weak"
    return {
        "status": status,
        "overlap_ratio": overlap_ratio,
        "shared_terms": shared_terms,
    }


def find_duplicate_heading_groups(headings: dict[str, list[str]]) -> list[dict[str, Any]]:
    counts = Counter()
    for heading_values in headings.values():
        for value in heading_values:
            normalized = clean_text(value)
            if not normalized:
                continue
            counts[normalized] += 1
    return [
        {"text": text, "count": count}
        for text, count in counts.items()
        if count > 1
    ]
