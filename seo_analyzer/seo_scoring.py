from typing import Any

from .seo_models import IndexabilityDict
from .seo_utils import GOOD_READABILITY_THRESHOLD, clamp_score


def _get_status_key(values: dict[str, Any], key: str) -> str | None:
    value = values.get(key)
    return value if isinstance(value, str) else None


def _get_weight(weights: dict[str, int], status: str | None) -> int:
    if status is None:
        return 0
    return weights.get(status, 0)


def score_meta_quality(meta_data: dict[str, Any]) -> float:
    score = 0.0
    title_weights = {"good": 25, "short": 10, "long": 10, "missing": 0}
    description_weights = {"good": 20, "short": 8, "long": 8, "missing": 0}
    canonical_weights = {"good": 20, "cross_domain": 2, "invalid": 0, "missing": 5}
    viewport_weights = {"good": 10, "partial": 5, "invalid": 0, "missing": 0}

    score += _get_weight(title_weights, _get_status_key(meta_data, "title_status"))
    score += _get_weight(description_weights, _get_status_key(meta_data, "description_status"))
    score += _get_weight(canonical_weights, _get_status_key(meta_data, "canonical_status"))
    score += _get_weight(viewport_weights, _get_status_key(meta_data, "viewport_status"))

    robots_status = meta_data.get("robots_status")
    if robots_status == "valid":
        score += 10
    elif robots_status == "default":
        score += 8
    elif robots_status == "restrictive":
        score += 0

    if meta_data.get("language"):
        score += 5

    social_score = 0
    if meta_data.get("og:title"):
        social_score += 2
    if meta_data.get("og:description"):
        social_score += 2
    if meta_data.get("og:image"):
        social_score += 1
    if meta_data.get("twitter:title"):
        social_score += 2
    if meta_data.get("twitter:description"):
        social_score += 2
    if meta_data.get("twitter:card"):
        social_score += 1
    score += min(social_score, 10)

    return clamp_score(score)


def score_content_quality(content_data: dict[str, Any]) -> float:
    score = 0.0
    h1_count = len(content_data["headings"].get("h1", []))
    if h1_count == 1:
        score += 22
    elif h1_count > 1:
        score += 10

    if content_data["primary_content_found"]:
        score += 15
        if content_data.get("primary_content_selector") in {"main", "article"}:
            score += 5

    target_word_count = max(content_data.get("target_word_count", 1), 1)
    word_count_ratio = content_data["word_count"] / target_word_count
    if word_count_ratio >= 1:
        score += 20
    elif word_count_ratio >= 0.75:
        score += 14
    elif word_count_ratio >= 0.5:
        score += 8
    elif content_data["word_count"] > 0:
        score += 4

    alignment_status = content_data["title_h1_alignment"]["status"]
    if alignment_status == "good":
        score += 15
    elif alignment_status == "partial":
        score += 8

    if not content_data["duplicate_headings"]:
        score += 10
    elif len(content_data["duplicate_headings"]) == 1:
        score += 4

    if content_data["page_type"] in {"article", "documentation", "generic"} and content_data["readability_score"] is not None:
        if content_data["readability_score"] >= GOOD_READABILITY_THRESHOLD:
            score += 8
        elif content_data["readability_score"] >= 30:
            score += 4
    else:
        score += 4

    image_total = content_data["image_alt_analysis"]["total"]
    if image_total == 0:
        score += 5
    else:
        alt_ratio = content_data["image_alt_analysis"]["with_alt"] / image_total
        if alt_ratio >= 0.9:
            score += 5
        elif alt_ratio >= 0.5:
            score += 3

    return clamp_score(score)


def score_link_quality(link_data: dict[str, Any]) -> float:
    total_links = link_data["internal_count"] + link_data["external_count"]
    if total_links == 0:
        return 0.0

    score = 0.0
    if link_data["internal_count"] >= 3:
        score += 45
    elif link_data["internal_count"] > 0:
        score += 25

    if link_data["external_count"] > 0:
        score += 10

    empty_anchor_ratio = link_data["anchor_texts"]["[Empty Anchor]"] / total_links
    descriptive_anchor_count = sum(
        1 for text in link_data["anchor_texts"] if text != "[Empty Anchor]" and len(text.split()) >= 2
    )
    if empty_anchor_ratio == 0 and descriptive_anchor_count >= 2:
        score += 35
    elif empty_anchor_ratio < 0.2:
        score += 20
    elif empty_anchor_ratio < 0.5:
        score += 10

    if link_data["internal_count"] > 0 and link_data["external_count"] > 0:
        score += 10

    live_status = link_data.get("live_status", {})
    if live_status.get("checked"):
        if live_status.get("broken_count", 0) == 0 and live_status.get("warning_count", 0) == 0:
            score += 10
        else:
            score -= live_status.get("broken_count", 0) * 7
            score -= live_status.get("warning_count", 0) * 2

    return clamp_score(score)


def score_technical_quality(tech_data: dict[str, Any]) -> float:
    score = 0.0
    if tech_data["https_status"] == "good":
        score += 25

    if tech_data["load_time_status"] == "good":
        score += 20
    elif tech_data["load_time_status"] == "warning":
        score += 10

    if tech_data["mobile_friendly"]["status"] == "good":
        score += 15
    elif tech_data["mobile_friendly"]["status"] == "warning":
        score += 8

    if tech_data["robots_txt"]["status"] == "Found":
        score += 10
    if "Found" in tech_data["sitemap_xml"]["status"]:
        score += 15
    if tech_data["schema_markup"]["present"]:
        score += 15
    if tech_data["performance_hints"]["status"] == "good":
        score += 5
    elif tech_data["performance_hints"]["status"] == "warning":
        score += 2

    indexability = tech_data["indexability"]
    if indexability["can_be_indexed"]:
        score += 10
    elif len(indexability["blockers"]) == 1:
        score -= 15
    else:
        score -= 25

    return clamp_score(score)


def score_indexability(indexability: IndexabilityDict) -> float:
    if not indexability["can_be_indexed"]:
        return 0.0
    if indexability["warnings"]:
        return 75.0
    return 100.0


def compute_overall_score(
    meta_score: float,
    content_score: float,
    link_score: float,
    tech_score: float,
    indexability: IndexabilityDict,
) -> float:
    overall_score = (
        score_indexability(indexability) * 0.35
        + content_score * 0.25
        + meta_score * 0.20
        + link_score * 0.10
        + tech_score * 0.10
    )
    if not indexability["can_be_indexed"]:
        overall_score = min(overall_score, 35.0)
    elif indexability["warnings"]:
        overall_score = min(overall_score, 85.0)
    return clamp_score(overall_score)
