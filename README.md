# 📊 Comprehensive SEO Meta Tag Analyzer

A Streamlit-based web application for inspecting SEO-relevant HTML signals on a webpage. It is best used as a fast heuristic checker for metadata, content structure, links, and selected technical signals.

## 🚀 Features

### Meta Tag Analysis
- Title tag evaluation
- Meta description analysis
- Canonical URL verification
- Robots meta tag detection
- Complete Open Graph and Twitter Card validation
- Language and charset verification
- Favicon detection

### Content Analysis
- Word count measurement
- Readability scoring (Flesch Reading Ease)
- Heading structure analysis (H1-H6)
- Keyword density analysis
- Image alt text validation
- Content structure evaluation

### Link Analysis
- Internal and external link counting
- Anchor text analysis
- Link distribution insights
- Generic anchor text detection

### Technical SEO
- HTTPS security check
- Server-side fetch time measurement
- Viewport-based mobile hint
- robots.txt verification
- sitemap.xml detection
- Schema markup (Structured Data) validation
- Viewport configuration check

### Prioritized Findings
- Structured issue list with severity and recommended fixes
- Validation-aware checks for title, description, canonical, robots, schema, and viewport
- Regression-tested handling for DOM mutation, malformed schema, and same-site subdomain links

## 📋 Requirements

```
streamlit>=1.10.0
requests>=2.25.1
beautifulsoup4>=4.9.3
textstat>=0.7.3
lxml>=4.9.0  # Optional but recommended parser for BeautifulSoup
```

## 🛠️ Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/marketing-seo-meta-tag-analyzer.git
cd marketing-seo-meta-tag-analyzer
```

2. Install the required packages:
```bash
pip install -r requirements.txt
```

## 💻 Usage

1. Start the Streamlit app:
```bash
streamlit run app.py
```

2. Open your web browser and navigate to the provided local URL (typically http://localhost:8501)

3. Enter any webpage URL to analyze

4. Review the score, structured findings, and detailed analysis tabs

## 📊 Analysis Categories

The tool provides scores and insights in four main categories:

1. **Meta & Social Tags** (20% of overall score)
   - Essential meta tags
   - Social media optimization
   - Language and regional settings

2. **On-Page Content** (35% of overall score)
   - Content quality and length
   - Readability
   - Heading structure
   - Image optimization

3. **Link Analysis** (15% of overall score)
   - Internal linking
   - External linking
   - Anchor text quality

4. **Technical SEO** (30% of overall score)
   - Security
   - Performance
   - Mobile optimization
   - Crawlability

## 🎯 Scoring System

The tool uses a weighted scoring system to calculate the overall SEO score:
- Scores are derived from rule-based HTML checks and heuristic signals
- Each category has specific scoring criteria
- The final score is weighted based on the importance of each category
- Scores range from 0-100, but should be treated as indicative rather than authoritative

## ⚠️ Limitations

- The tool analyzes fetched HTML and does not execute JavaScript-rendered content
- Load time is measured from the analyzer server and is not a real-user performance metric
- Mobile analysis is based on viewport configuration, not rendered layout or device testing
- Some checks are validated HTML rules, while others remain heuristics
- Duplicate content detection is limited to canonical tag checking
- Live broken-link validation is not performed

## ✅ Accuracy Notes

- Strongest signals: tag presence, canonical formatting, robots.txt lookup, sitemap detection, schema parsing, and heading/image/link extraction from static HTML
- Weaker signals: readability, keyword density, score weighting, server fetch time, and viewport-based mobile interpretation
- Best fit: server-rendered or mostly static pages
- Lower confidence: JavaScript-heavy pages where important content is injected after initial HTML

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

If you encounter any issues or have questions, please open an issue in the GitHub repository.

---

*Disclaimer: This tool provides automated analysis based on common SEO best practices. A comprehensive SEO strategy should include manual review and industry expertise.*
