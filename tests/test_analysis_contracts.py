from pathlib import Path
import unittest

from seo_analysis import analyze_html_document, should_attempt_rendered_fetch
from seo_utils import parse_x_robots_tag


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class AnalysisContractTests(unittest.TestCase):
    def test_complex_article_fixture_returns_expected_contract_shape(self):
        html = load_fixture("complex_article.html")

        results = analyze_html_document(
            html,
            "https://example.com/blog/technical-seo-audit-checklist",
            load_time=1.2,
            response_headers={"content-type": "text/html; charset=utf-8"},
        )

        self.assertEqual(
            set(results.keys()),
            {
                "meta_data",
                "meta_score",
                "content_data",
                "content_score",
                "link_data",
                "link_score",
                "tech_data",
                "tech_score",
                "warnings",
                "issues",
                "overall_score",
            },
        )
        self.assertEqual(results["content_data"]["page_type"], "article")
        self.assertEqual(results["meta_data"]["title_status"], "good")
        self.assertTrue(results["tech_data"]["schema_markup"]["present"])
        self.assertGreater(results["content_data"]["word_count"], 80)

    def test_non_html_documents_are_marked_not_indexable(self):
        html = load_fixture("complex_article.html")

        results = analyze_html_document(
            html,
            "https://example.com/report.pdf",
            load_time=0.8,
            response_headers={"content-type": "application/pdf"},
            is_html_document=False,
        )

        self.assertFalse(results["tech_data"]["indexability"]["can_be_indexed"])
        self.assertIn("response_not_html", results["tech_data"]["indexability"]["blockers"])

    def test_prefixed_x_robots_directives_are_normalized(self):
        directives = parse_x_robots_tag(
            {
                "X-Robots-Tag": "googlebot: noindex, nofollow, unavailable_after: 25 Jun 2026 15:00:00 PST"
            }
        )

        self.assertIn("noindex", directives)
        self.assertIn("nofollow", directives)
        self.assertIn("25 jun 2026 15:00:00 pst", directives)

    def test_fixture_client_shell_triggers_render_recommendation(self):
        html = load_fixture("client_rendered_shell.html")

        self.assertTrue(should_attempt_rendered_fetch(html))
