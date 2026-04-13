from typing import Any, TypedDict


class IssueDict(TypedDict):
    category: str
    severity: str
    message: str
    evidence: dict[str, Any]
    recommendation: str | None


class IndexabilityDict(TypedDict):
    can_be_indexed: bool
    status: str
    blockers: list[str]
    warnings: list[str]
    canonical_target: str | None
    x_robots_tag: list[str]


class AnalysisResult(TypedDict):
    meta_data: dict[str, Any]
    meta_score: float
    content_data: dict[str, Any]
    content_score: float
    link_data: dict[str, Any]
    link_score: float
    tech_data: dict[str, Any]
    tech_score: float
    warnings: list[str]
    issues: list[IssueDict]
    overall_score: float
