import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import seo_storage
from seo_storage import (
    add_monitor,
    build_scan_record,
    compare_scan_records,
    find_previous_scan,
    get_monitor_status,
    save_scan_record,
)


def make_scan(scan_id, created_at, average_score, non_indexable_pages, missing_title_urls=None):
    missing_title_urls = missing_title_urls or []
    pages = [
        {
            "final_url": "https://example.com/",
            "indexable": non_indexable_pages == 0,
            "overall_score": average_score,
            "high_issue_count": 1 if non_indexable_pages else 0,
        }
    ]
    return {
        "id": scan_id,
        "created_at": created_at,
        "scan_kind": "site_audit",
        "target": "https://example.com",
        "target_key": "site_audit:https|example.com|/|",
        "source": "crawl",
        "config": {"fetch_mode": "auto", "discovery_mode": "crawl"},
        "pages": pages,
        "summary": {
            "average_score": average_score,
            "non_indexable_pages": non_indexable_pages,
            "pages_analyzed": 1,
            "missing_by_field": {
                "title": missing_title_urls,
                "description": [],
                "h1": [],
                "canonical": [],
            },
            "duplicate_titles": [],
            "duplicate_descriptions": [],
            "duplicate_h1s": [],
        },
    }


class SeoStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

        self.data_dir.mkdir(exist_ok=True)
        self.patches = [
            patch.object(seo_storage, "DATA_DIR", self.data_dir),
            patch.object(seo_storage, "SCAN_HISTORY_PATH", self.data_dir / "scan_history.json"),
            patch.object(seo_storage, "MONITORS_PATH", self.data_dir / "monitors.json"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_compare_scan_records_detects_regressions(self):
        previous = make_scan("prev", "2026-04-01T00:00:00+00:00", 82.0, 0, [])
        current = make_scan("curr", "2026-04-02T00:00:00+00:00", 61.0, 1, ["https://example.com/"])

        comparison = compare_scan_records(current, previous)

        self.assertTrue(comparison["has_regressions"])
        self.assertIn("average_score_down", comparison["regressions"])
        self.assertIn("more_non_indexable_pages", comparison["regressions"])
        self.assertIn("title", comparison["missing_field_regressions"])

    def test_save_scan_and_find_previous_scan(self):
        previous = build_scan_record(
            "site_audit",
            "https://example.com",
            pages=[],
            summary={"average_score": 80, "non_indexable_pages": 0, "pages_analyzed": 0, "missing_by_field": {"title": [], "description": [], "h1": [], "canonical": []}, "duplicate_titles": [], "duplicate_descriptions": [], "duplicate_h1s": []},
            config={"fetch_mode": "auto"},
        )
        current = build_scan_record(
            "site_audit",
            "https://example.com",
            pages=[],
            summary={"average_score": 75, "non_indexable_pages": 0, "pages_analyzed": 0, "missing_by_field": {"title": [], "description": [], "h1": [], "canonical": []}, "duplicate_titles": [], "duplicate_descriptions": [], "duplicate_h1s": []},
            config={"fetch_mode": "auto"},
        )

        save_scan_record(previous)
        save_scan_record(current)

        found = find_previous_scan(current)

        self.assertIsNotNone(found)
        self.assertEqual(found["id"], previous["id"])

    def test_monitor_status_uses_latest_comparison(self):
        previous = make_scan("prev", "2026-04-01T00:00:00+00:00", 82.0, 0, [])
        current = make_scan("curr", "2026-04-02T00:00:00+00:00", 61.0, 1, ["https://example.com/"])
        save_scan_record(previous)
        save_scan_record(current)

        monitor = add_monitor("Example", "site_audit", "https://example.com", {"fetch_mode": "auto"})
        status = get_monitor_status(monitor)

        self.assertEqual(status["state"], "regression")
        self.assertEqual(status["latest_scan"]["id"], "curr")


if __name__ == "__main__":
    unittest.main()
