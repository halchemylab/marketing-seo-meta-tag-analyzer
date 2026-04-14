import unittest
from unittest.mock import patch

from seo_audit import build_site_audit_summary, parse_sitemap_xml, run_site_audit


class SeoAuditTests(unittest.TestCase):
    def test_parse_sitemap_xml_extracts_urls(self):
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/blog</loc></url>
</urlset>
"""

        parsed = parse_sitemap_xml(xml_content)

        self.assertEqual(parsed["urls"], ["https://example.com/", "https://example.com/blog"])
        self.assertEqual(parsed["sitemaps"], [])

    def test_build_site_audit_summary_groups_duplicates_and_missing_fields(self):
        pages = [
            {
                "final_url": "https://example.com/",
                "fetch_error": None,
                "overall_score": 88.0,
                "indexable": True,
                "page_type": "homepage",
                "issues": [{"message": "Meta description is missing.", "severity": "high"}],
                "title": "Example Home",
                "title_status": "good",
                "description": None,
                "description_status": "missing",
                "canonical_status": "good",
                "primary_h1": "SEO monitoring",
                "h1_count": 1,
                "high_issue_count": 1,
                "medium_issue_count": 0,
                "word_count": 120,
            },
            {
                "final_url": "https://example.com/pricing",
                "fetch_error": None,
                "overall_score": 52.0,
                "indexable": False,
                "page_type": "generic",
                "issues": [{"message": "Meta description is missing.", "severity": "high"}],
                "title": "Example Home",
                "title_status": "good",
                "description": None,
                "description_status": "missing",
                "canonical_status": "missing",
                "primary_h1": "Pricing",
                "h1_count": 1,
                "high_issue_count": 1,
                "medium_issue_count": 0,
                "word_count": 45,
            },
        ]

        summary = build_site_audit_summary(pages)

        self.assertEqual(summary["pages_analyzed"], 2)
        self.assertEqual(summary["non_indexable_pages"], 1)
        self.assertEqual(summary["missing_by_field"]["description"], ["https://example.com/", "https://example.com/pricing"])
        self.assertEqual(summary["missing_by_field"]["canonical"], ["https://example.com/pricing"])
        self.assertEqual(summary["duplicate_titles"][0]["value"], "Example Home")
        self.assertEqual(summary["top_issues"][0]["message"], "Meta description is missing.")

    @patch("seo_audit.audit_from_url_list")
    @patch("seo_audit.discover_sitemap_urls")
    def test_run_site_audit_prefers_sitemap_results_in_auto_mode(self, mock_discover_sitemap_urls, mock_audit_from_url_list):
        mock_discover_sitemap_urls.return_value = (["https://example.com/", "https://example.com/blog"], [])
        mock_audit_from_url_list.return_value = {
            "pages": [{"final_url": "https://example.com/", "fetch_error": None}],
            "summary": {"pages_analyzed": 1},
            "warnings": [],
        }

        report = run_site_audit("https://example.com", discovery_mode="auto", max_urls=10)

        self.assertEqual(report["source"], "sitemap")
        self.assertEqual(report["pages"][0]["final_url"], "https://example.com/")
        mock_audit_from_url_list.assert_called_once_with(
            ["https://example.com/", "https://example.com/blog"],
            fetch_mode="auto",
        )


if __name__ == "__main__":
    unittest.main()
