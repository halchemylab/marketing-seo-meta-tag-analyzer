import unittest

from seo_analysis import analyze_html_document


BASE_URL = "https://example.com/page"


HTML_WITH_NAV_AND_FOOTER = """
<!doctype html>
<html lang="en">
<head>
  <title>Short</title>
  <meta name="description" content="Too short">
  <meta name="viewport" content="width=device-width">
  <link rel="canonical" href="https://example.com/page">
</head>
<body>
  <nav>
    <a href="/home">Home</a>
    <a href="https://blog.example.com/article">Blog</a>
  </nav>
  <main>
    <h1>Main heading</h1>
    <p>This page has enough words to exercise parsing behavior without trying to be realistic.
    It exists so that link classification and DOM isolation can be tested with confidence.</p>
    <a href="/inside">Inside</a>
    <img src="/hero.jpg">
  </main>
  <footer>
    <a href="/contact">Contact</a>
  </footer>
</body>
</html>
"""


HTML_WITH_BROKEN_SCHEMA = """
<!doctype html>
<html>
<head>
  <title>This is a reasonably sized title for testing</title>
  <meta name="description" content="This is a reasonably sized meta description for testing the validation logic in the SEO analyzer output.">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="canonical" href="https://other-site.com/page">
  <script type="application/ld+json">{ not-valid-json }</script>
</head>
<body>
  <h1>Heading</h1>
  <p>Simple content for schema validation.</p>
  <a href="https://example.com/next">Next</a>
</body>
</html>
"""


HTML_WITH_NOINDEX = """
<!doctype html>
<html lang="en">
<head>
  <title>This is a reasonably sized title for testing</title>
  <meta name="description" content="This is a reasonably sized meta description for testing the validation logic in the SEO analyzer output.">
  <meta name="robots" content="noindex, follow">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="canonical" href="https://example.com/page">
</head>
<body>
  <main>
    <h1>Primary heading</h1>
    <p>This page includes enough text to avoid unrelated failures while testing indexability logic.</p>
  </main>
</body>
</html>
"""


HTML_HOMEPAGE = """
<!doctype html>
<html lang="en">
<head>
  <title>Example Platform for SEO Teams</title>
  <meta name="description" content="Example Platform helps SEO teams monitor websites, report on technical health, and improve metadata quality at scale.">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="canonical" href="https://example.com/">
</head>
<body>
  <header><nav><a href="/features">Features</a><a href="/pricing">Pricing</a></nav></header>
  <main>
    <h1>SEO monitoring for modern teams</h1>
    <p>Track crawlers, metadata, and page health from one dashboard.</p>
    <p>Ship fixes faster with automated issue prioritization and alerts.</p>
    <p>Review title tags, canonicals, robots signals, schema, and internal linking from a single workspace.</p>
    <p>Share clear recommendations with content, engineering, and leadership without digging through multiple tools.</p>
    <p>Monitor technical SEO health daily, compare page templates, and catch indexability regressions before they affect traffic.</p>
  </main>
  <footer><a href="/contact">Contact</a></footer>
</body>
</html>
"""


HTML_WITH_TITLE_H1_MISMATCH = """
<!doctype html>
<html lang="en">
<head>
  <title>Enterprise Security Automation Platform</title>
  <meta name="description" content="A descriptive meta description that is long enough for the analyzer to treat as valid for this test fixture.">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="canonical" href="https://example.com/platform">
</head>
<body>
  <main>
    <h1>Organic Coffee Beans Subscription</h1>
    <p>This fixture is intentionally mismatched so the analyzer can flag weak intent alignment between the title and the primary heading.</p>
  </main>
</body>
</html>
"""


class SeoAnalysisTests(unittest.TestCase):
    def test_content_analysis_does_not_remove_links_from_other_analyzers(self):
        results = analyze_html_document(HTML_WITH_NAV_AND_FOOTER, BASE_URL, load_time=1.5)
        self.assertEqual(results["link_data"]["internal_count"], 4)
        self.assertEqual(results["link_data"]["external_count"], 0)

    def test_broken_schema_does_not_count_as_valid_schema(self):
        results = analyze_html_document(HTML_WITH_BROKEN_SCHEMA, BASE_URL, load_time=1.5)
        self.assertFalse(results["tech_data"]["schema_markup"]["present"])
        self.assertIn("Error Parsing", results["tech_data"]["schema_markup"]["types"])

    def test_cross_domain_canonical_is_flagged(self):
        results = analyze_html_document(HTML_WITH_BROKEN_SCHEMA, BASE_URL, load_time=1.5)
        self.assertEqual(results["meta_data"]["canonical_status"], "cross_domain")
        self.assertTrue(any(issue["message"] == "Canonical URL points to a different site." for issue in results["issues"]))

    def test_short_title_and_description_are_reported(self):
        results = analyze_html_document(HTML_WITH_NAV_AND_FOOTER, BASE_URL, load_time=1.5)
        messages = {issue["message"] for issue in results["issues"]}
        self.assertEqual(results["meta_data"]["title_status"], "short")
        self.assertEqual(results["meta_data"]["description_status"], "short")
        self.assertIn("Title tag is too short.", messages)
        self.assertIn("Meta description is short.", messages)

    def test_meta_noindex_blocks_indexability(self):
        results = analyze_html_document(HTML_WITH_NOINDEX, BASE_URL, load_time=1.5)
        self.assertFalse(results["tech_data"]["indexability"]["can_be_indexed"])
        self.assertIn("meta_noindex", results["tech_data"]["indexability"]["blockers"])
        self.assertTrue(
            any(issue["message"] == "Page is unlikely to be indexable by search engines." for issue in results["issues"])
        )

    def test_x_robots_noindex_blocks_indexability(self):
        results = analyze_html_document(
            HTML_WITH_NAV_AND_FOOTER,
            BASE_URL,
            load_time=1.5,
            response_headers={"X-Robots-Tag": "noindex, nofollow"},
        )
        self.assertFalse(results["tech_data"]["indexability"]["can_be_indexed"])
        self.assertIn("x_robots_noindex", results["tech_data"]["indexability"]["blockers"])

    def test_same_site_non_self_canonical_triggers_indexability_warning(self):
        html = """
<!doctype html>
<html lang="en">
<head>
  <title>This is a reasonably sized title for testing</title>
  <meta name="description" content="This is a reasonably sized meta description for testing the validation logic in the SEO analyzer output.">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="canonical" href="https://example.com/other-page">
</head>
<body>
  <main>
    <h1>Primary heading</h1>
    <p>This page includes enough text to avoid unrelated failures while testing indexability logic.</p>
  </main>
</body>
</html>
"""
        results = analyze_html_document(html, BASE_URL, load_time=1.5)
        self.assertTrue(results["tech_data"]["indexability"]["can_be_indexed"])
        self.assertIn(
            "canonical_points_to_different_same_site_url",
            results["tech_data"]["indexability"]["warnings"],
        )

    def test_homepage_uses_page_type_specific_word_count_target(self):
        results = analyze_html_document(HTML_HOMEPAGE, "https://example.com/", load_time=1.5)
        self.assertEqual(results["content_data"]["page_type"], "homepage")
        self.assertEqual(results["content_data"]["target_word_count"], 60)
        self.assertNotIn(
            "Main content is thin for this page type.",
            {issue["message"] for issue in results["issues"]},
        )

    def test_title_h1_mismatch_is_reported(self):
        results = analyze_html_document(HTML_WITH_TITLE_H1_MISMATCH, "https://example.com/platform", load_time=1.5)
        self.assertEqual(results["content_data"]["title_h1_alignment"]["status"], "weak")
        self.assertIn(
            "Title and primary H1 are weakly aligned.",
            {issue["message"] for issue in results["issues"]},
        )


if __name__ == "__main__":
    unittest.main()
