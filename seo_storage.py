from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from seo_audit import build_site_audit_summary, normalize_url_key, summarize_page_result

DATA_DIR = Path(__file__).parent / "data"
SCAN_HISTORY_PATH = DATA_DIR / "scan_history.json"
MONITORS_PATH = DATA_DIR / "monitors.json"


def ensure_storage() -> None:
    DATA_DIR.mkdir(exist_ok=True)


def load_json_file(path: Path, default: Any) -> Any:
    ensure_storage()
    if not path.exists():
        return deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return deepcopy(default)


def write_json_file(path: Path, payload: Any) -> None:
    ensure_storage()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_target_key(scan_kind: str, target: str) -> str:
    return f"{scan_kind}:{normalize_url_key(target)}"


def build_scan_record(
    scan_kind: str,
    target: str,
    pages: list[dict[str, Any]],
    summary: dict[str, Any],
    config: dict[str, Any],
    source: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "created_at": utc_now_iso(),
        "scan_kind": scan_kind,
        "target": target,
        "target_key": make_target_key(scan_kind, target),
        "source": source,
        "config": config,
        "summary": summary,
        "pages": pages,
    }


def build_single_page_scan_record(url: str, result: dict[str, Any], fetch_mode: str) -> dict[str, Any]:
    page = summarize_page_result(result, url)
    summary = build_site_audit_summary([page])
    summary["fetch_strategy"] = result.get("fetch_strategy", "static")
    summary["render_recommended"] = result.get("render_recommended", False)
    return build_scan_record(
        "single_page",
        page["final_url"],
        [page],
        summary,
        {"fetch_mode": fetch_mode},
        source="single",
    )


def build_site_audit_scan_record(report: dict[str, Any]) -> dict[str, Any]:
    return build_scan_record(
        "site_audit",
        report["target"],
        report["pages"],
        report["summary"],
        {
            "fetch_mode": report["fetch_mode"],
            "discovery_mode": report["discovery_mode"],
        },
        source=report.get("source"),
    )


def save_scan_record(record: dict[str, Any]) -> None:
    history = load_json_file(SCAN_HISTORY_PATH, [])
    history.append(record)
    write_json_file(SCAN_HISTORY_PATH, history)


def get_scan_history(limit: int | None = None) -> list[dict[str, Any]]:
    history = load_json_file(SCAN_HISTORY_PATH, [])
    history.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    if limit is None:
        return history
    return history[:limit]


def find_previous_scan(record: dict[str, Any]) -> dict[str, Any] | None:
    for item in get_scan_history():
        if item["id"] == record["id"]:
            continue
        if item["target_key"] == record["target_key"]:
            return item
    return None


def compare_scan_records(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any] | None:
    if previous is None:
        return None

    current_summary = current["summary"]
    previous_summary = previous["summary"]

    current_pages = {page["final_url"]: page for page in current["pages"]}
    previous_pages = {page["final_url"]: page for page in previous["pages"]}

    newly_non_indexable = sorted(
        url
        for url, page in current_pages.items()
        if url in previous_pages and not page["indexable"] and previous_pages[url]["indexable"]
    )
    score_drops = []
    for url, page in current_pages.items():
        previous_page = previous_pages.get(url)
        if not previous_page:
            continue
        delta = round(page["overall_score"] - previous_page["overall_score"], 1)
        if delta <= -10:
            score_drops.append({"url": url, "delta": delta})
    score_drops.sort(key=lambda item: item["delta"])

    missing_field_regressions = {}
    for field, current_urls in current_summary["missing_by_field"].items():
        previous_urls = set(previous_summary["missing_by_field"].get(field, []))
        new_urls = sorted(url for url in current_urls if url not in previous_urls)
        if new_urls:
            missing_field_regressions[field] = new_urls

    current_duplicates = {
        "titles": len(current_summary["duplicate_titles"]),
        "descriptions": len(current_summary["duplicate_descriptions"]),
        "h1s": len(current_summary["duplicate_h1s"]),
    }
    previous_duplicates = {
        "titles": len(previous_summary["duplicate_titles"]),
        "descriptions": len(previous_summary["duplicate_descriptions"]),
        "h1s": len(previous_summary["duplicate_h1s"]),
    }

    new_high_issue_pages = sorted(
        url
        for url, page in current_pages.items()
        if url in previous_pages and page["high_issue_count"] > previous_pages[url]["high_issue_count"]
    )

    regressions = []
    if current_summary["average_score"] < previous_summary["average_score"]:
        regressions.append("average_score_down")
    if current_summary["non_indexable_pages"] > previous_summary["non_indexable_pages"]:
        regressions.append("more_non_indexable_pages")
    if missing_field_regressions:
        regressions.append("new_missing_metadata")
    if newly_non_indexable:
        regressions.append("newly_non_indexable_urls")
    if score_drops:
        regressions.append("page_score_drops")
    if any(current_duplicates[key] > previous_duplicates[key] for key in current_duplicates):
        regressions.append("more_duplicate_metadata")
    if new_high_issue_pages:
        regressions.append("more_high_priority_issues")

    return {
        "previous_scan_id": previous["id"],
        "previous_created_at": previous["created_at"],
        "average_score_delta": round(current_summary["average_score"] - previous_summary["average_score"], 1),
        "non_indexable_delta": current_summary["non_indexable_pages"] - previous_summary["non_indexable_pages"],
        "pages_analyzed_delta": current_summary["pages_analyzed"] - previous_summary["pages_analyzed"],
        "newly_non_indexable": newly_non_indexable,
        "score_drops": score_drops[:10],
        "missing_field_regressions": missing_field_regressions,
        "duplicate_delta": {
            key: current_duplicates[key] - previous_duplicates[key]
            for key in current_duplicates
        },
        "new_high_issue_pages": new_high_issue_pages[:10],
        "has_regressions": bool(regressions),
        "regressions": regressions,
    }


def add_monitor(name: str, scan_kind: str, target: str, config: dict[str, Any]) -> dict[str, Any]:
    monitors = load_json_file(MONITORS_PATH, [])
    target_key = make_target_key(scan_kind, target)
    existing = next((item for item in monitors if item["target_key"] == target_key), None)
    if existing:
        existing["name"] = name
        existing["config"] = config
        existing["updated_at"] = utc_now_iso()
        write_json_file(MONITORS_PATH, monitors)
        return existing

    monitor = {
        "id": str(uuid4()),
        "name": name,
        "scan_kind": scan_kind,
        "target": target,
        "target_key": target_key,
        "config": config,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    monitors.append(monitor)
    write_json_file(MONITORS_PATH, monitors)
    return monitor


def get_monitors() -> list[dict[str, Any]]:
    monitors = load_json_file(MONITORS_PATH, [])
    monitors.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return monitors


def get_monitor_status(monitor: dict[str, Any]) -> dict[str, Any]:
    matching_scans = [scan for scan in get_scan_history() if scan["target_key"] == monitor["target_key"]]
    latest_scan = matching_scans[0] if matching_scans else None
    previous_scan = matching_scans[1] if len(matching_scans) > 1 else None
    comparison = compare_scan_records(latest_scan, previous_scan) if latest_scan else None

    if latest_scan is None:
        state = "no-data"
    elif comparison is None:
        state = "baseline"
    elif comparison["has_regressions"]:
        state = "regression"
    else:
        state = "stable"

    return {
        "monitor": monitor,
        "latest_scan": latest_scan,
        "previous_scan": previous_scan,
        "comparison": comparison,
        "state": state,
    }
