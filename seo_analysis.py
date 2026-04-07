import json
import re
import time
from collections import Counter
from copy import deepcopy
from urllib.parse import urljoin, urlparse

import requests
import textstat
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = 15
MIN_CONTENT_LENGTH_WORDS = 300
GOOD_LOAD_TIME_THRESHOLD = 2.0
OK_LOAD_TIME_THRESHOLD = 4.0
GOOD_READABILITY_THRESHOLD = 60
MAX_KEYWORDS_TO_SHOW = 10
TITLE_MIN_LENGTH = 15
TITLE_MAX_LENGTH = 60
DESCRIPTION_MIN_LENGTH = 70
DESCRIPTION_MAX_LENGTH = 160


def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def fetch_content(url):
    warnings = []
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
        return response.content, response.url, load_time, None, warnings, response.headers
    except requests.exceptions.Timeout:
        return None, url, None, f"Error: Request timed out after {REQUEST_TIMEOUT} seconds.", warnings, {}
    except requests.exceptions.RequestException as exc:
        return None, url, None, f"Error fetching URL: {exc}", warnings, {}
    except Exception as exc:
        return None, url, None, f"An unexpected error occurred during fetch: {exc}", warnings, {}


def parse_html(html_content):
    try:
        return BeautifulSoup(html_content, "lxml")
    except Exception:
        return BeautifulSoup(html_content, "html.parser")


def get_domain(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return None


def normalize_netloc(netloc):
    if not netloc:
        return ""
    return netloc.lower().split(":")[0].removeprefix("www.")


def site_key(netloc):
    normalized = normalize_netloc(netloc)
    parts = normalized.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return normalized


def is_same_site(url_a, url_b):
    return site_key(get_domain(url_a)) == site_key(get_domain(url_b))


def validate_length(text, min_length, max_length):
    if not text:
        return "missing"
    text_length = len(text.strip())
    if min_length <= text_length <= max_length:
        return "good"
    if text_length < min_length:
        return "short"
    return "long"


def validate_canonical_url(page_url, canonical_url):
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


def normalize_url_for_comparison(url):
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


def parse_robots_directives(content):
    if not content:
        return set()
    return {directive.strip().lower() for directive in content.split(",") if directive.strip()}


def parse_x_robots_tag(headers):
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


def validate_viewport_content(content):
    if not content:
        return "missing"
    normalized = content.replace(" ", "").lower()
    if "width=device-width" not in normalized:
        return "invalid"
    if "initial-scale=1" in normalized:
        return "good"
    return "partial"


def extract_schema_types(schema_json):
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


def build_issue(category, severity, message, evidence=None, recommendation=None):
    return {
        "category": category,
        "severity": severity,
        "message": message,
        "evidence": evidence or {},
        "recommendation": recommendation,
    }


def clean_text(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def evaluate_indexability(page_url, meta_data, response_headers=None, is_html_document=True):
    indexability = {
        "can_be_indexed": True,
        "status": "indexable",
        "blockers": [],
        "warnings": [],
        "canonical_target": meta_data.get("canonical"),
        "x_robots_tag": [],
    }

    x_robots_directives = parse_x_robots_tag(response_headers or {})
    indexability["x_robots_tag"] = x_robots_directives

    meta_robots_directives = set(meta_data.get("robots_directives", []))
    x_robots_directives_set = set(x_robots_directives)

    if not is_html_document:
        indexability["blockers"].append("response_not_html")

    if "noindex" in meta_robots_directives or "none" in meta_robots_directives:
        indexability["blockers"].append("meta_noindex")
    if "noindex" in x_robots_directives_set or "none" in x_robots_directives_set:
        indexability["blockers"].append("x_robots_noindex")

    canonical_status = meta_data.get("canonical_status")
    canonical_target = meta_data.get("canonical")
    if canonical_status == "invalid":
        indexability["blockers"].append("invalid_canonical")
    elif canonical_status == "cross_domain":
        indexability["blockers"].append("cross_domain_canonical")
    elif canonical_status == "good" and canonical_target:
        if normalize_url_for_comparison(page_url) != normalize_url_for_comparison(canonical_target):
            indexability["warnings"].append("canonical_points_to_different_same_site_url")

    robots_status = meta_data.get("robots_status")
    if robots_status == "conflict":
        indexability["warnings"].append("conflicting_meta_robots")
    if "unavailable_after" in meta_robots_directives or "unavailable_after" in x_robots_directives_set:
        indexability["warnings"].append("time_limited_indexing")

    if indexability["blockers"]:
        indexability["can_be_indexed"] = False
        indexability["status"] = "blocked"
    elif indexability["warnings"]:
        indexability["status"] = "caution"

    return indexability


def analyze_meta_tags(soup, url):
    meta_data = {
        "title": None,
        "title_status": "missing",
        "description": None,
        "description_status": "missing",
        "keywords": None,
        "robots": None,
        "robots_directives": [],
        "robots_status": "default",
        "canonical": None,
        "canonical_status": "missing",
        "og:title": None,
        "og:description": None,
        "og:image": None,
        "og:url": None,
        "twitter:title": None,
        "twitter:description": None,
        "twitter:image": None,
        "twitter:card": None,
        "viewport": None,
        "author": None,
        "charset": None,
        "language": None,
        "favicon": None,
        "alternate": [],
        "viewport_status": "missing",
        "indexability": None,
    }
    scoring = {"points": 0, "max_points": 28}

    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        meta_data["title"] = title_tag.string.strip()
        meta_data["title_status"] = validate_length(meta_data["title"], TITLE_MIN_LENGTH, TITLE_MAX_LENGTH)
        if meta_data["title_status"] == "good":
            scoring["points"] += 5
        elif meta_data["title_status"] in {"short", "long"}:
            scoring["points"] += 2

    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag and desc_tag.get("content"):
        meta_data["description"] = desc_tag["content"].strip()
        meta_data["description_status"] = validate_length(
            meta_data["description"],
            DESCRIPTION_MIN_LENGTH,
            DESCRIPTION_MAX_LENGTH,
        )
        if meta_data["description_status"] == "good":
            scoring["points"] += 4
        elif meta_data["description_status"] in {"short", "long"}:
            scoring["points"] += 2

    keywords_tag = soup.find("meta", attrs={"name": "keywords"})
    if keywords_tag and keywords_tag.get("content"):
        meta_data["keywords"] = keywords_tag["content"].strip()

    robots_tag = soup.find("meta", attrs={"name": "robots"})
    if robots_tag and robots_tag.get("content"):
        meta_data["robots"] = robots_tag["content"].strip()
        directives = parse_robots_directives(meta_data["robots"])
        meta_data["robots_directives"] = sorted(directives)
        if {"noindex", "index"} <= directives or {"nofollow", "follow"} <= directives:
            meta_data["robots_status"] = "conflict"
        elif "noindex" in directives or "nofollow" in directives:
            meta_data["robots_status"] = "restrictive"
            scoring["points"] += 0.5
        else:
            meta_data["robots_status"] = "valid"
            scoring["points"] += 1

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    if canonical_tag and canonical_tag.get("href"):
        meta_data["canonical"] = urljoin(url, canonical_tag["href"])
        meta_data["canonical_status"] = validate_canonical_url(url, meta_data["canonical"])
        if meta_data["canonical_status"] == "good":
            scoring["points"] += 3
        elif meta_data["canonical_status"] == "cross_domain":
            scoring["points"] += 1

    og_tags = soup.find_all("meta", property=lambda value: value and value.startswith("og:"))
    for tag in og_tags:
        prop = tag.get("property")
        content = tag.get("content")
        if prop and content:
            meta_data[prop] = content.strip()
    if (
        meta_data.get("og:title")
        and meta_data.get("og:description")
        and meta_data.get("og:image")
    ):
        scoring["points"] += 3

    twitter_tags = soup.find_all("meta", attrs={"name": lambda value: value and value.startswith("twitter:")})
    for tag in twitter_tags:
        name = tag.get("name")
        content = tag.get("content")
        if name and content:
            meta_data[name] = content.strip()
    if (
        meta_data.get("twitter:card")
        and meta_data.get("twitter:title")
        and meta_data.get("twitter:description")
    ):
        scoring["points"] += 2

    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    if viewport_tag and viewport_tag.get("content"):
        meta_data["viewport"] = viewport_tag["content"].strip()
        meta_data["viewport_status"] = validate_viewport_content(meta_data["viewport"])
        if meta_data["viewport_status"] == "good":
            scoring["points"] += 3
        elif meta_data["viewport_status"] == "partial":
            scoring["points"] += 1

    author_tag = soup.find("meta", attrs={"name": "author"})
    if author_tag and author_tag.get("content"):
        meta_data["author"] = author_tag["content"].strip()
        scoring["points"] += 1

    charset_tag = soup.find("meta", charset=True)
    if charset_tag and charset_tag.get("charset"):
        meta_data["charset"] = charset_tag["charset"].strip()
        scoring["points"] += 1
    else:
        http_equiv_tag = soup.find("meta", attrs={"http-equiv": "Content-Type"})
        if http_equiv_tag and "charset=" in http_equiv_tag.get("content", ""):
            try:
                meta_data["charset"] = http_equiv_tag["content"].split("charset=")[-1].strip()
                scoring["points"] += 1
            except Exception:
                pass

    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        meta_data["language"] = html_tag["lang"].strip()
        scoring["points"] += 1

    favicons = soup.find_all("link", rel=lambda value: value and "icon" in value.lower())
    if favicons:
        preferred_favicon = soup.find("link", rel="icon") or soup.find("link", rel="shortcut icon")
        if preferred_favicon and preferred_favicon.get("href"):
            meta_data["favicon"] = urljoin(url, preferred_favicon["href"])
        elif favicons[0].get("href"):
            meta_data["favicon"] = urljoin(url, favicons[0]["href"])
        if meta_data["favicon"]:
            scoring["points"] += 1

    alt_tags = soup.find_all("link", attrs={"rel": "alternate", "hreflang": True, "href": True})
    for tag in alt_tags:
        meta_data["alternate"].append(
            {"hreflang": tag.get("hreflang"), "href": urljoin(url, tag.get("href"))}
        )
    if meta_data["alternate"]:
        scoring["points"] += 3

    meta_score = (scoring["points"] / scoring["max_points"]) * 100 if scoring["max_points"] > 0 else 0
    return meta_data, meta_score


def analyze_on_page_content(soup):
    content_data = {
        "headings": {},
        "word_count": 0,
        "readability_score": None,
        "readability_desc": "Not calculated",
        "top_keywords": [],
        "image_alt_analysis": {"total": 0, "with_alt": 0, "missing_alt": 0, "alt_tags": []},
        "text_content": "",
    }
    scoring = {"points": 0, "max_points": 30}

    heading_tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    has_h1 = False
    heading_hierarchy_ok = True
    last_level = 0
    for heading in heading_tags:
        level = int(heading.name[1])
        text = heading.get_text(strip=True)
        if not text:
            continue
        content_data["headings"].setdefault(heading.name, []).append(text)
        if heading.name == "h1":
            has_h1 = True
        if level > last_level + 1 and last_level != 0:
            heading_hierarchy_ok = False
        last_level = level

    if has_h1:
        scoring["points"] += 5
        if len(content_data["headings"].get("h1", [])) > 1:
            scoring["points"] -= 2
            heading_hierarchy_ok = False
    if heading_hierarchy_ok and has_h1:
        scoring["points"] += 3
    elif has_h1:
        scoring["points"] += 1

    body = deepcopy(soup.find("body"))
    if body:
        for element in body(["script", "style", "nav", "footer", "aside"]):
            element.decompose()
        raw_text = body.get_text(separator=" ", strip=True)
        content_data["text_content"] = raw_text
        content_data["word_count"] = len(raw_text.split())

    if content_data["word_count"] >= MIN_CONTENT_LENGTH_WORDS:
        scoring["points"] += 5
    elif content_data["word_count"] > 0:
        scoring["points"] += 2

    if content_data["word_count"] > 50:
        try:
            content_data["readability_score"] = textstat.flesch_reading_ease(content_data["text_content"])
            score = content_data["readability_score"]
            if score >= GOOD_READABILITY_THRESHOLD:
                content_data["readability_desc"] = f"Good ({score:.1f} - Fairly easy to read)"
                scoring["points"] += 5
            elif score >= 30:
                content_data["readability_desc"] = f"Okay ({score:.1f} - Plain English)"
                scoring["points"] += 2
            else:
                content_data["readability_desc"] = f"Difficult ({score:.1f} - Very confusing)"
        except Exception:
            content_data["readability_desc"] = "Calculation Error"
    else:
        content_data["readability_desc"] = "Not enough content to calculate"

    if content_data["word_count"] > 0:
        cleaned_text = clean_text(content_data["text_content"])
        words = cleaned_text.split()
        stop_words = {
            "a",
            "an",
            "the",
            "and",
            "or",
            "but",
            "is",
            "in",
            "it",
            "of",
            "to",
            "on",
            "for",
            "with",
            "as",
            "by",
            "at",
            "this",
            "that",
            "i",
            "you",
            "he",
            "she",
            "we",
            "they",
            "be",
            "are",
            "was",
            "were",
            "has",
            "have",
            "had",
            "do",
            "does",
            "did",
            "will",
            "shall",
            "should",
            "can",
            "could",
            "may",
            "might",
            "must",
            "not",
            "no",
            "so",
            "if",
            "me",
            "my",
            "your",
            "our",
            "its",
            "-",
            "",
        }
        meaningful_words = [word for word in words if word not in stop_words and len(word) > 2]
        if meaningful_words:
            word_counts = Counter(meaningful_words)
            total_meaningful_words = len(meaningful_words)
            for word, count in word_counts.most_common(MAX_KEYWORDS_TO_SHOW):
                density = (count / total_meaningful_words) * 100 if total_meaningful_words > 0 else 0
                content_data["top_keywords"].append((word, count, density))
            if content_data["top_keywords"]:
                scoring["points"] += 5

    images = soup.find_all("img")
    content_data["image_alt_analysis"]["total"] = len(images)
    for img in images:
        alt_text = img.get("alt", "").strip()
        src = img.get("src", "No Source")
        if alt_text:
            content_data["image_alt_analysis"]["with_alt"] += 1
            content_data["image_alt_analysis"]["alt_tags"].append(
                {"src": src, "alt": alt_text, "status": "present"}
            )
        else:
            content_data["image_alt_analysis"]["missing_alt"] += 1
            content_data["image_alt_analysis"]["alt_tags"].append(
                {"src": src, "alt": None, "status": "missing"}
            )

    if content_data["image_alt_analysis"]["total"] > 0:
        alt_percentage = (
            content_data["image_alt_analysis"]["with_alt"] / content_data["image_alt_analysis"]["total"]
        ) * 100
        if alt_percentage >= 90:
            scoring["points"] += 4
        elif alt_percentage >= 50:
            scoring["points"] += 2
    else:
        scoring["points"] += 4

    content_score = (scoring["points"] / scoring["max_points"]) * 100 if scoring["max_points"] > 0 else 0
    return content_data, content_score


def analyze_links(soup, base_url):
    link_data = {
        "internal": [],
        "external": [],
        "internal_count": 0,
        "external_count": 0,
        "anchor_texts": Counter(),
        "links_all": [],
    }
    scoring = {"points": 0, "max_points": 15}
    base_domain = get_domain(base_url)

    links = soup.find_all("a", href=True)
    for link in links:
        href = link["href"]
        anchor_text = link.get_text(strip=True)
        full_url = urljoin(base_url, href)

        if anchor_text:
            link_data["anchor_texts"][anchor_text] += 1
        else:
            link_data["anchor_texts"]["[Empty Anchor]"] += 1

        link_info = {"href": full_url, "text": anchor_text}
        parsed_href = urlparse(full_url)
        if not parsed_href.scheme or parsed_href.scheme not in ["http", "https"]:
            link_info["type"] = "other"
            link_data["links_all"].append(link_info)
            continue

        link_domain = get_domain(full_url)
        if site_key(link_domain) == site_key(base_domain):
            link_data["internal"].append(full_url)
            link_data["internal_count"] += 1
            link_info["type"] = "internal"
        else:
            link_data["external"].append(full_url)
            link_data["external_count"] += 1
            link_info["type"] = "external"

        link_data["links_all"].append(link_info)

    total_links = link_data["internal_count"] + link_data["external_count"]
    if total_links > 0:
        scoring["points"] += 5
        if link_data["internal_count"] > 0 and link_data["external_count"] > 0 and total_links > 5:
            scoring["points"] += 5
        if (
            len(link_data["anchor_texts"]) > 3
            and link_data["anchor_texts"]["[Empty Anchor]"] < total_links * 0.5
        ):
            scoring["points"] += 5
        elif len(link_data["anchor_texts"]) > 1:
            scoring["points"] += 2

    link_score = (scoring["points"] / scoring["max_points"]) * 100 if scoring["max_points"] > 0 else 0
    return link_data, link_score


def analyze_technical_seo(url, soup, load_time, meta_data, response_headers=None, is_html_document=True):
    tech_data = {
        "robots_txt": {"status": "Not Checked", "content": None, "url": None},
        "sitemap_xml": {"status": "Not Checked", "url": None, "found_in_robots": False},
        "load_time": load_time,
        "load_time_status": "info",
        "mobile_friendly": {"status": "Not Checked", "reason": ""},
        "https_status": "info",
        "schema_markup": {"present": False, "types": [], "details": []},
        "indexability": evaluate_indexability(
            url,
            meta_data,
            response_headers=response_headers,
            is_html_document=is_html_document,
        ),
    }
    scoring = {"points": 0, "max_points": 27}
    warnings = []

    parsed_url = urlparse(url)
    base_url_scheme_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

    if parsed_url.scheme == "https":
        tech_data["https_status"] = "good"
        scoring["points"] += 3
    else:
        tech_data["https_status"] = "bad"

    robots_url = urljoin(base_url_scheme_domain, "/robots.txt")
    tech_data["robots_txt"]["url"] = robots_url
    sitemap_directive_found = None
    try:
        robots_res = requests.get(robots_url, headers=HEADERS, timeout=10)
        if robots_res.status_code == 200:
            tech_data["robots_txt"]["status"] = "Found"
            tech_data["robots_txt"]["content"] = robots_res.text
            scoring["points"] += 4
            for line in robots_res.text.splitlines():
                if line.strip().lower().startswith("sitemap:"):
                    sitemap_directive_found = line.strip().split(":", 1)[1].strip()
                    tech_data["sitemap_xml"]["found_in_robots"] = True
                    tech_data["sitemap_xml"]["url"] = sitemap_directive_found
                    break
        elif robots_res.status_code == 404:
            tech_data["robots_txt"]["status"] = "Not Found"
        else:
            tech_data["robots_txt"]["status"] = f"Error (Status: {robots_res.status_code})"
    except requests.exceptions.RequestException as exc:
        tech_data["robots_txt"]["status"] = f"Error fetching: {exc}"

    sitemap_urls_to_check = [sitemap_directive_found] if sitemap_directive_found else [
        urljoin(base_url_scheme_domain, "/sitemap.xml"),
        urljoin(base_url_scheme_domain, "/sitemap_index.xml"),
    ]
    sitemap_found = False
    for sitemap_url in sitemap_urls_to_check:
        if sitemap_found:
            break
        tech_data["sitemap_xml"]["url"] = sitemap_url
        try:
            sitemap_res = requests.head(sitemap_url, headers=HEADERS, timeout=10, allow_redirects=True)
            if sitemap_res.status_code == 200:
                tech_data["sitemap_xml"]["status"] = "Found"
                sitemap_found = True
                scoring["points"] += 5
                break
            if sitemap_res.status_code != 404:
                sitemap_res_get = requests.get(
                    sitemap_url, headers=HEADERS, timeout=10, allow_redirects=True
                )
                if sitemap_res_get.status_code == 200:
                    tech_data["sitemap_xml"]["status"] = "Found"
                    sitemap_found = True
                    scoring["points"] += 5
                    break
                if sitemap_res_get.status_code == 404:
                    tech_data["sitemap_xml"]["status"] = "Not Found"
                else:
                    tech_data["sitemap_xml"]["status"] = f"Error (Status: {sitemap_res_get.status_code})"
        except requests.exceptions.RequestException:
            tech_data["sitemap_xml"]["status"] = "Error Fetching"
    if not sitemap_found:
        tech_data["sitemap_xml"]["status"] = "Not Found (Common Locations)"

    if load_time is not None:
        if load_time <= GOOD_LOAD_TIME_THRESHOLD:
            tech_data["load_time_status"] = "good"
            scoring["points"] += 7
        elif load_time <= OK_LOAD_TIME_THRESHOLD:
            tech_data["load_time_status"] = "warning"
            scoring["points"] += 3
        else:
            tech_data["load_time_status"] = "bad"
    else:
        tech_data["load_time_status"] = "error"

    viewport_content = meta_data.get("viewport")
    if viewport_content:
        viewport_status = validate_viewport_content(viewport_content)
        if viewport_status == "good":
            tech_data["mobile_friendly"]["status"] = "good"
            tech_data["mobile_friendly"]["reason"] = "Viewport tag correctly configured."
            scoring["points"] += 5
        elif viewport_status == "partial":
            tech_data["mobile_friendly"]["status"] = "warning"
            tech_data["mobile_friendly"]["reason"] = (
                "Viewport tag found, but might lack `initial-scale=1`."
            )
            scoring["points"] += 2
        else:
            tech_data["mobile_friendly"]["status"] = "bad"
            tech_data["mobile_friendly"]["reason"] = (
                "Viewport tag present but seems incorrectly configured."
            )
    else:
        tech_data["mobile_friendly"]["status"] = "bad"
        tech_data["mobile_friendly"]["reason"] = "Viewport meta tag not found."

    schema_tags = soup.find_all("script", type="application/ld+json")
    for tag in schema_tags:
        try:
            schema_json = json.loads(tag.string or "")
            tech_data["schema_markup"]["present"] = True
            tech_data["schema_markup"]["details"].append(schema_json)
            tech_data["schema_markup"]["types"].extend(extract_schema_types(schema_json))
        except json.JSONDecodeError:
            tech_data["schema_markup"]["types"].append("Error Parsing")
            warnings.append("Found schema tag (application/ld+json) but could not parse its content.")
        except Exception:
            tech_data["schema_markup"]["types"].append("Error Processing")

    valid_schema_types = [
        schema_type for schema_type in tech_data["schema_markup"]["types"]
        if schema_type not in {"Error Parsing", "Error Processing"}
    ]
    if valid_schema_types:
        tech_data["schema_markup"]["present"] = True
        scoring["points"] += 3
    else:
        tech_data["schema_markup"]["present"] = False

    tech_score = (scoring["points"] / scoring["max_points"]) * 100 if scoring["max_points"] > 0 else 0
    return tech_data, tech_score, warnings


def generate_issues(meta_data, content_data, link_data, tech_data):
    issues = []
    indexability = tech_data["indexability"]

    if not indexability["can_be_indexed"]:
        issues.append(
            build_issue(
                "technical",
                "high",
                "Page is unlikely to be indexable by search engines.",
                evidence={"blockers": indexability["blockers"]},
                recommendation="Resolve the indexing blockers before relying on the page for organic search visibility.",
            )
        )
    elif indexability["warnings"]:
        issues.append(
            build_issue(
                "technical",
                "medium",
                "Page has indexability warnings that may affect the preferred indexed URL.",
                evidence={"warnings": indexability["warnings"]},
                recommendation="Review robots and canonical signals to ensure search engines can index the intended URL.",
            )
        )

    if meta_data["title_status"] == "missing":
        issues.append(build_issue("meta", "high", "Title tag is missing.", recommendation="Add a unique title tag."))
    elif meta_data["title_status"] == "short":
        issues.append(build_issue("meta", "medium", "Title tag is too short.", evidence={"title": meta_data["title"]}, recommendation="Expand the title to better describe the page intent."))
    elif meta_data["title_status"] == "long":
        issues.append(build_issue("meta", "medium", "Title tag is too long.", evidence={"title": meta_data["title"]}, recommendation="Trim the title to reduce truncation risk in search results."))

    if meta_data["description_status"] == "missing":
        issues.append(build_issue("meta", "high", "Meta description is missing.", recommendation="Add a descriptive meta description."))
    elif meta_data["description_status"] in {"short", "long"}:
        issues.append(build_issue("meta", "medium", f"Meta description is {meta_data['description_status']}.", evidence={"description": meta_data["description"]}, recommendation="Adjust the meta description length to fit common search snippet ranges."))

    if meta_data["canonical_status"] == "missing":
        issues.append(build_issue("meta", "medium", "Canonical tag is missing.", recommendation="Add a self-referencing canonical URL when appropriate."))
    elif meta_data["canonical_status"] == "invalid":
        issues.append(build_issue("meta", "high", "Canonical URL is invalid.", evidence={"canonical": meta_data["canonical"]}, recommendation="Use an absolute canonical URL without fragments."))
    elif meta_data["canonical_status"] == "cross_domain":
        issues.append(build_issue("meta", "medium", "Canonical URL points to a different site.", evidence={"canonical": meta_data["canonical"]}, recommendation="Verify that the cross-domain canonical is intentional."))

    if meta_data["robots_status"] == "conflict":
        issues.append(build_issue("meta", "high", "Robots meta tag contains conflicting directives.", evidence={"robots": meta_data["robots"]}, recommendation="Remove contradictory robots directives."))
    elif meta_data["robots_status"] == "restrictive":
        issues.append(build_issue("meta", "medium", "Robots meta tag contains restrictive directives.", evidence={"robots": meta_data["robots"]}, recommendation="Confirm that `noindex` or `nofollow` is intentional."))

    if meta_data["viewport_status"] == "missing":
        issues.append(build_issue("technical", "high", "Viewport tag is missing.", recommendation="Add a responsive viewport meta tag."))
    elif meta_data["viewport_status"] == "invalid":
        issues.append(build_issue("technical", "high", "Viewport tag is invalid.", evidence={"viewport": meta_data["viewport"]}, recommendation="Use `width=device-width, initial-scale=1`."))
    elif meta_data["viewport_status"] == "partial":
        issues.append(build_issue("technical", "medium", "Viewport tag is incomplete.", evidence={"viewport": meta_data["viewport"]}, recommendation="Include both `width=device-width` and `initial-scale=1`."))

    if len(content_data["headings"].get("h1", [])) == 0:
        issues.append(build_issue("content", "high", "No H1 heading was found.", recommendation="Add a single primary H1 heading to the page."))
    elif len(content_data["headings"].get("h1", [])) > 1:
        issues.append(build_issue("content", "medium", "Multiple H1 headings were found.", evidence={"h1_count": len(content_data["headings"].get("h1", []))}, recommendation="Consolidate to one primary H1 where possible."))

    if content_data["word_count"] < MIN_CONTENT_LENGTH_WORDS:
        issues.append(build_issue("content", "medium", "Main content is thin.", evidence={"word_count": content_data["word_count"]}, recommendation="Expand the main body content if the page is intended to rank organically."))

    missing_alt = content_data["image_alt_analysis"]["missing_alt"]
    if missing_alt > 0:
        issues.append(build_issue("content", "medium", "Some images are missing alt text.", evidence={"missing_alt": missing_alt}, recommendation="Add meaningful alt text to informative images."))

    if link_data["internal_count"] == 0:
        issues.append(build_issue("links", "medium", "No internal links were detected.", recommendation="Link to relevant pages on the same site."))
    if link_data["anchor_texts"]["[Empty Anchor]"] > 0:
        issues.append(build_issue("links", "medium", "Some links have empty anchor text.", evidence={"empty_anchor_count": link_data["anchor_texts"]["[Empty Anchor]"]}, recommendation="Ensure linked elements have descriptive accessible names."))

    if tech_data["https_status"] != "good":
        issues.append(build_issue("technical", "high", "Page is not using HTTPS.", recommendation="Serve the page over HTTPS."))
    if tech_data["robots_txt"]["status"] != "Found":
        issues.append(build_issue("technical", "low", "robots.txt was not found.", evidence={"status": tech_data["robots_txt"]["status"]}, recommendation="Publish a robots.txt file if the site should guide crawlers."))
    if "Found" not in tech_data["sitemap_xml"]["status"]:
        issues.append(build_issue("technical", "low", "Sitemap was not detected in common locations.", evidence={"status": tech_data["sitemap_xml"]["status"]}, recommendation="Expose a sitemap and reference it from robots.txt."))
    if not tech_data["schema_markup"]["present"]:
        issues.append(build_issue("technical", "low", "Valid schema markup was not detected.", recommendation="Add valid JSON-LD where it adds search value."))

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda issue: (severity_rank.get(issue["severity"], 3), issue["category"], issue["message"]))
    return issues


def analyze_html_document(html_content, url, load_time=None, response_headers=None, is_html_document=True):
    soup = parse_html(html_content)
    meta_data, meta_score = analyze_meta_tags(soup, url)
    content_data, content_score = analyze_on_page_content(soup)
    link_data, link_score = analyze_links(soup, url)
    tech_data, tech_score, warnings = analyze_technical_seo(
        url,
        soup,
        load_time,
        meta_data,
        response_headers=response_headers,
        is_html_document=is_html_document,
    )
    meta_data["indexability"] = tech_data["indexability"]
    issues = generate_issues(meta_data, content_data, link_data, tech_data)
    overall_score = (
        meta_score * 0.20 +
        content_score * 0.35 +
        link_score * 0.15 +
        tech_score * 0.30
    )
    return {
        "meta_data": meta_data,
        "meta_score": meta_score,
        "content_data": content_data,
        "content_score": content_score,
        "link_data": link_data,
        "link_score": link_score,
        "tech_data": tech_data,
        "tech_score": tech_score,
        "warnings": warnings,
        "issues": issues,
        "overall_score": overall_score,
    }


def analyze_url(url):
    html_content, final_url, load_time, fetch_error, warnings, response_headers = fetch_content(url)
    if fetch_error or html_content is None:
        return {
            "html_content": html_content,
            "final_url": final_url,
            "load_time": load_time,
            "fetch_error": fetch_error,
            "warnings": warnings,
            "response_headers": response_headers,
        }

    content_type = (response_headers or {}).get("content-type", "").lower()
    analysis_results = analyze_html_document(
        html_content,
        final_url,
        load_time=load_time,
        response_headers=response_headers,
        is_html_document="text/html" in content_type,
    )
    warnings.extend(analysis_results["warnings"])

    return {
        "html_content": html_content,
        "final_url": final_url,
        "load_time": load_time,
        "fetch_error": None,
        "warnings": warnings,
        "response_headers": response_headers,
        **analysis_results,
    }
