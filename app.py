import streamlit as st

from seo_analysis import GOOD_READABILITY_THRESHOLD, MAX_KEYWORDS_TO_SHOW, analyze_url, is_valid_url

MAX_LINKS_TO_SHOW = 15


def get_status_icon(status):
    if status == "good":
        return "✅"
    if status == "warning":
        return "⚠️"
    if status == "bad":
        return "❌"
    return "ℹ️"


def display_metric_card(label, value, status="info", help_text=None):
    icon = get_status_icon(status)
    st.metric(label=f"{icon} {label}", value=value, help=help_text)


st.set_page_config(page_title="Comprehensive SEO Parser", layout="wide", initial_sidebar_state="collapsed")

st.title("📊 Comprehensive SEO Parser")
st.markdown("Enter a URL to analyze its SEO elements. Results are based on common best practices.")

url_input = st.text_input("Enter URL (e.g., https://www.example.com):", key="url_input")

if st.button("Analyze URL", key="analyze_button"):
    if not url_input:
        st.warning("Please enter a URL.")
    elif not is_valid_url(url_input):
        st.error("Invalid URL format. Please include 'http://' or 'https://'.")
    else:
        with st.spinner(f"Fetching and analyzing {url_input}... This may take a moment."):
            results = analyze_url(url_input)

        if results["fetch_error"]:
            st.error(results["fetch_error"])
            st.stop()

        for warning in results["warnings"]:
            st.warning(warning)

        final_url = results["final_url"]
        meta_data = results["meta_data"]
        meta_score = results["meta_score"]
        content_data = results["content_data"]
        content_score = results["content_score"]
        link_data = results["link_data"]
        link_score = results["link_score"]
        tech_data = results["tech_data"]
        tech_score = results["tech_score"]
        overall_score = results["overall_score"]
        issues = results["issues"]

        if url_input.lower() != final_url.lower():
            st.info(f"Note: URL redirected to: {final_url}")

        st.success(f"Analysis Complete for: {final_url}")

        st.header("🚀 Overall SEO Score")
        st.progress(int(overall_score) / 100)
        st.metric(label="Overall Score", value=f"{overall_score:.1f}%")
        st.markdown("---")

        if issues:
            st.subheader("Priority Fixes")
            severity_icons = {"high": "❌", "medium": "⚠️", "low": "ℹ️"}
            for issue in issues[:5]:
                st.markdown(
                    f"{severity_icons.get(issue['severity'], 'ℹ️')} "
                    f"**[{issue['severity'].upper()}] {issue['message']}** "
                    f"{issue['recommendation'] or ''}"
                )
            st.caption("These recommendations are generated from validated checks and heuristic rules in the current analyzer.")
            st.markdown("---")

        st.subheader("📊 Score Breakdown")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Meta & Social Tags", f"{meta_score:.1f}%")
            st.progress(int(meta_score) / 100)
        with col2:
            st.metric("On-Page Content", f"{content_score:.1f}%")
            st.progress(int(content_score) / 100)
        with col3:
            st.metric("Link Analysis", f"{link_score:.1f}%")
            st.progress(int(link_score) / 100)
        with col4:
            st.metric("Technical SEO", f"{tech_score:.1f}%")
            st.progress(int(tech_score) / 100)

        st.markdown("---")

        tab_meta, tab_content, tab_links, tab_tech = st.tabs(
            ["🏷️ Meta & Social", "📝 On-Page Content", "🔗 Links", "⚙️ Technical SEO"]
        )

        with tab_meta:
            st.subheader("Meta Tag Analysis")
            st.markdown("These tags tell search engines and social media platforms about your page.")

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                display_metric_card(
                    "Title Tag",
                    meta_data.get("title") or "Missing",
                    "good" if meta_data.get("title_status") == "good" else ("warning" if meta_data.get("title") else "bad"),
                    "The main title shown in search results and browser tabs.",
                )
                display_metric_card(
                    "Meta Description",
                    meta_data.get("description") or "Missing",
                    "good" if meta_data.get("description_status") == "good" else ("warning" if meta_data.get("description") else "bad"),
                    "Summary shown below the title in search results.",
                )
                display_metric_card(
                    "Canonical URL",
                    meta_data.get("canonical") or "Missing",
                    "good" if meta_data.get("canonical_status") == "good" else ("warning" if meta_data.get("canonical") else "bad"),
                    "Specifies the preferred version of this page.",
                )
                display_metric_card(
                    "Robots Meta Tag",
                    meta_data.get("robots") or "Default (index, follow)",
                    "good" if meta_data.get("robots_status") == "valid" else ("warning" if meta_data.get("robots") else "info"),
                    "Instructions for search engine crawlers (e.g., 'noindex').",
                )
                display_metric_card(
                    "Viewport Tag",
                    meta_data.get("viewport") or "Missing",
                    "good" if meta_data.get("viewport_status") == "good" else ("warning" if meta_data.get("viewport") else "bad"),
                    "Essential for making the page responsive on mobile devices.",
                )
            with col_m2:
                display_metric_card(
                    "Character Set (Charset)",
                    meta_data.get("charset") or "Not Found",
                    "good" if meta_data.get("charset") else "warning",
                    "Ensures text displays correctly (UTF-8 recommended).",
                )
                display_metric_card(
                    "Language",
                    meta_data.get("language") or "Not Specified",
                    "good" if meta_data.get("language") else "warning",
                    "Helps search engines understand the page language.",
                )
                display_metric_card(
                    "Favicon",
                    meta_data.get("favicon") or "Missing",
                    "good" if meta_data.get("favicon") else "info",
                    "Small icon shown in browser tabs.",
                )
                display_metric_card(
                    "Author",
                    meta_data.get("author") or "Not Specified",
                    "info",
                    "Specifies the page author (less common).",
                )
                display_metric_card(
                    "Keywords Meta Tag",
                    meta_data.get("keywords") or "Not Found",
                    "info",
                    "List of keywords (mostly ignored by Google now).",
                )

            st.subheader("Social Media Tags (Open Graph & Twitter)")
            st.markdown(
                "These tags control how your page looks when shared on platforms like Facebook and Twitter."
            )
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.markdown("**Open Graph (Facebook, LinkedIn, etc.)**")
                display_metric_card("OG Title", meta_data.get("og:title") or "Missing", "good" if meta_data.get("og:title") else "warning")
                display_metric_card("OG Description", meta_data.get("og:description") or "Missing", "good" if meta_data.get("og:description") else "warning")
                display_metric_card("OG Image", meta_data.get("og:image") or "Missing", "good" if meta_data.get("og:image") else "warning")
                display_metric_card("OG URL", meta_data.get("og:url") or "Missing", "info")
            with col_s2:
                st.markdown("**Twitter Card**")
                display_metric_card("Twitter Card Type", meta_data.get("twitter:card") or "Missing", "good" if meta_data.get("twitter:card") else "warning")
                display_metric_card("Twitter Title", meta_data.get("twitter:title") or "Missing", "good" if meta_data.get("twitter:title") else "warning")
                display_metric_card("Twitter Description", meta_data.get("twitter:description") or "Missing", "good" if meta_data.get("twitter:description") else "warning")
                display_metric_card("Twitter Image", meta_data.get("twitter:image") or "Missing", "good" if meta_data.get("twitter:image") else "warning")

            if meta_data.get("alternate"):
                with st.expander("Alternate Language/Region Links (hreflang)"):
                    st.markdown("Found alternate versions specified for different languages or regions:")
                    for alt in meta_data["alternate"]:
                        st.write(f"- **Lang/Region:** `{alt.get('hreflang')}` → **URL:** `{alt.get('href')}`")

        with tab_content:
            st.subheader("Content Analysis")
            st.markdown("Analyzes the text content, structure, and accessibility elements on the page.")

            col_c1, col_c2 = st.columns(2)
            wc_status = (
                "good"
                if content_data["word_count"] >= content_data["target_word_count"]
                else ("warning" if content_data["word_count"] > 0 else "bad")
            )
            with col_c1:
                display_metric_card(
                    "Word Count",
                    f"{content_data['word_count']} words",
                    wc_status,
                    f"Total words found in the primary content area. Target for detected page type ({content_data['page_type']}): {content_data['target_word_count']}+",
                )
            with col_c2:
                readability_status = "info"
                if content_data["readability_score"] is not None:
                    if content_data["readability_score"] >= GOOD_READABILITY_THRESHOLD:
                        readability_status = "good"
                    elif content_data["readability_score"] >= 30:
                        readability_status = "warning"
                    else:
                        readability_status = "bad"
                display_metric_card(
                    "Readability (Flesch Score)",
                    content_data["readability_desc"],
                    readability_status,
                    "Score indicating how easy the text is to read. This is emphasized for article, documentation, and generic pages.",
                )

            display_metric_card(
                "Detected Page Type",
                content_data["page_type"].replace("_", " ").title(),
                "info",
                "Used to adjust content expectations so product, category, homepage, and article pages are not judged the same way.",
            )
            if content_data.get("primary_content_selector"):
                st.caption(
                    f"Primary content extracted from `{content_data['primary_content_selector']}` for content scoring."
                )

            st.subheader("Heading Structure (H1-H6)")
            if content_data["headings"]:
                h1_count = len(content_data["headings"].get("h1", []))
                if h1_count == 1:
                    st.success(
                        f"{get_status_icon('good')} Found exactly one H1 tag: `{content_data['headings']['h1'][0]}`"
                    )
                elif h1_count > 1:
                    st.warning(
                        f"{get_status_icon('warning')} Found {h1_count} H1 tags. Generally, only one H1 per page is recommended."
                    )
                    for h1_text in content_data["headings"]["h1"]:
                        st.markdown(f" - `{h1_text}`")
                else:
                    st.error(f"{get_status_icon('bad')} No H1 tag found. An H1 tag is crucial for defining the main topic.")

                with st.expander("View All Headings"):
                    for level in range(1, 7):
                        tag = f"h{level}"
                        if tag in content_data["headings"]:
                            st.markdown(f"**{tag.upper()} Tags:**")
                            for text in content_data["headings"][tag]:
                                st.markdown(f"- `{text}`")
            else:
                st.warning("No heading tags (H1-H6) found on the page.")

            st.subheader("Topic Terms (Informational)")
            if content_data["top_keywords"]:
                st.markdown(
                    f"Top {len(content_data['top_keywords'])} recurring terms found in the primary content. These are shown for inspection, not used as a direct SEO score signal:"
                )
                kw_data = [
                    {"Keyword": kw[0], "Count": kw[1], "Density (%)": f"{kw[2]:.2f}%"}
                    for kw in content_data["top_keywords"]
                ]
                st.dataframe(kw_data, use_container_width=True)
            else:
                st.info("No recurring terms could be extracted from the primary content.")

            alignment = content_data["title_h1_alignment"]
            st.subheader("Title and H1 Alignment")
            if alignment["status"] == "good":
                st.success("Title and primary H1 strongly align.")
            elif alignment["status"] == "partial":
                st.warning("Title and primary H1 partially align.")
            elif alignment["status"] == "weak":
                st.warning("Title and primary H1 appear weakly aligned.")
            else:
                st.info("Title/H1 alignment could not be calculated.")
            if alignment["shared_terms"]:
                st.caption(f"Shared terms: {', '.join(f'`{term}`' for term in alignment['shared_terms'])}")

            st.subheader("Image Alt Text Analysis")
            img_alt = content_data["image_alt_analysis"]
            if img_alt["total"] > 0:
                missing_perc = (img_alt["missing_alt"] / img_alt["total"]) * 100
                alt_status = "good" if missing_perc <= 10 else ("warning" if missing_perc <= 50 else "bad")
                display_metric_card("Images Found", img_alt["total"], "info")
                display_metric_card(
                    "Images Missing Alt Text",
                    f"{img_alt['missing_alt']} ({missing_perc:.1f}%)",
                    alt_status,
                    "Alt text describes images for search engines and visually impaired users. Aim for 0 missing.",
                )
                if img_alt["missing_alt"] > 0:
                    with st.expander(f"View Images Missing Alt Text ({img_alt['missing_alt']})"):
                        missing_alts = [item["src"] for item in img_alt["alt_tags"] if item["status"] == "missing"]
                        for index, src in enumerate(missing_alts):
                            st.markdown(f"- `{src if len(src) < 100 else src[:100] + '...'}`")
                            if index >= MAX_LINKS_TO_SHOW - 1:
                                st.markdown(f"...and {len(missing_alts) - MAX_LINKS_TO_SHOW} more")
                                break
            else:
                st.info("No images (`<img>` tags) found on the page.")

        with tab_links:
            st.subheader("Link Analysis")
            st.markdown("Examines the links pointing away from this page.")

            col_l1, col_l2 = st.columns(2)
            with col_l1:
                display_metric_card("Internal Links", link_data["internal_count"], "info", "Links pointing to other pages on the same website.")
            with col_l2:
                display_metric_card("External Links", link_data["external_count"], "info", "Links pointing to different websites.")

            total_links = link_data["internal_count"] + link_data["external_count"]
            if total_links > 0:
                with st.expander(f"View Internal Links ({link_data['internal_count']})", expanded=False):
                    if link_data["internal"]:
                        for index, link in enumerate(link_data["internal"]):
                            st.markdown(f"- `{link}`")
                            if index >= MAX_LINKS_TO_SHOW - 1:
                                st.markdown(f"...and {link_data['internal_count'] - MAX_LINKS_TO_SHOW} more")
                                break
                    else:
                        st.markdown("_No internal links found._")

                with st.expander(f"View External Links ({link_data['external_count']})", expanded=False):
                    if link_data["external"]:
                        for index, link in enumerate(link_data["external"]):
                            st.markdown(f"- `{link}`")
                            if index >= MAX_LINKS_TO_SHOW - 1:
                                st.markdown(f"...and {link_data['external_count'] - MAX_LINKS_TO_SHOW} more")
                                break
                    else:
                        st.markdown("_No external links found._")

                st.subheader("Anchor Text Analysis")
                st.markdown("The visible text used for links. Diverse and descriptive anchor text is generally good.")
                if link_data["anchor_texts"]:
                    with st.expander(f"View Anchor Text Usage (Top {MAX_KEYWORDS_TO_SHOW})"):
                        anchor_list = [
                            {"Anchor Text": text if text else "[Empty Anchor]", "Count": count}
                            for text, count in link_data["anchor_texts"].most_common(MAX_KEYWORDS_TO_SHOW)
                        ]
                        st.dataframe(anchor_list, use_container_width=True)
                        if link_data["anchor_texts"]["[Empty Anchor]"] > 0:
                            st.warning(
                                f"{get_status_icon('warning')} Found {link_data['anchor_texts']['[Empty Anchor]']} link(s) with empty or missing anchor text."
                            )
                        common_generic = ["click here", "learn more", "read more", "here"]
                        generic_anchors_found = [text for text in link_data["anchor_texts"] if text.lower() in common_generic]
                        if generic_anchors_found:
                            st.warning(
                                f"{get_status_icon('warning')} Found generic anchor text like: {', '.join(f'`{a}`' for a in generic_anchors_found)}. Use descriptive text instead."
                            )
                else:
                    st.info("No anchor text data to analyze.")

                st.info(f"{get_status_icon('info')} Note: This tool does not perform live checks for broken links due to performance reasons.")
            else:
                st.info("No internal or external links found on the page.")

        with tab_tech:
            st.subheader("Technical SEO Checks")
            st.markdown("Assesses technical aspects affecting crawlability, indexing, and performance.")

            col_t1, col_t2 = st.columns(2)
            with col_t1:
                https_status_map = {
                    "good": "✅ Using HTTPS",
                    "bad": "❌ Not Using HTTPS (Insecure)",
                    "info": "ℹ️ Could not determine",
                }
                st.markdown(
                    f"**{get_status_icon(tech_data['https_status'])} Security (HTTPS):** {https_status_map.get(tech_data['https_status'], 'Unknown')}"
                )

                lt_status = tech_data["load_time_status"]
                lt_text = f"{tech_data['load_time']:.2f} seconds" if tech_data["load_time"] is not None else "Error"
                lt_desc = "Good" if lt_status == "good" else ("Okay" if lt_status == "warning" else ("Slow" if lt_status == "bad" else "Error"))
                st.markdown(f"**{get_status_icon(lt_status)} Server Fetch Time:** {lt_text} ({lt_desc})")
                st.caption("This is a server-side fetch measurement, not a Core Web Vitals or real-user performance metric.")

                mf_status = tech_data["mobile_friendly"]["status"]
                mf_text = "Responsive Viewport Detected" if mf_status == "good" else ("Viewport Needs Review" if mf_status == "warning" else "No Responsive Viewport Signal")
                st.markdown(f"**{get_status_icon(mf_status)} Mobile Viewport Hint:** {mf_text}")
                st.caption(f"({tech_data['mobile_friendly']['reason']}) This is a viewport-based heuristic, not a rendered mobile usability test.")

            with col_t2:
                rb_status = tech_data["robots_txt"]["status"]
                rb_icon = get_status_icon("good" if rb_status == "Found" else ("bad" if rb_status == "Not Found" else "warning"))
                st.markdown(f"**{rb_icon} robots.txt Status:** {rb_status}")
                if tech_data["robots_txt"]["url"]:
                    st.caption(f"Checked at: `{tech_data['robots_txt']['url']}`")
                if rb_status == "Found" and tech_data["robots_txt"]["content"]:
                    with st.expander("View robots.txt Content"):
                        st.code(tech_data["robots_txt"]["content"], language="text")

                sm_status = tech_data["sitemap_xml"]["status"]
                sm_icon = get_status_icon("good" if "Found" in sm_status else ("bad" if "Not Found" in sm_status else "warning"))
                found_method = "(from robots.txt)" if tech_data["sitemap_xml"]["found_in_robots"] else "(common locations)"
                st.markdown(f"**{sm_icon} sitemap.xml Status:** {sm_status} {found_method}")
                if tech_data["sitemap_xml"]["url"]:
                    st.caption(f"Checked: `{tech_data['sitemap_xml']['url']}`")

                sc_present = tech_data["schema_markup"]["present"]
                st.markdown(
                    f"**{get_status_icon('good' if sc_present else 'info')} Schema Markup (Structured Data):** {'Present' if sc_present else 'Not Detected'}"
                )
                if sc_present and tech_data["schema_markup"]["types"]:
                    unique_types = sorted(set(tech_data["schema_markup"]["types"]))
                    st.caption(f"Detected types: {', '.join(f'`{schema_type}`' for schema_type in unique_types)}")

            st.markdown("---")
            st.info(
                f"{get_status_icon('info')} **Duplicate Content:** This tool checks for a `canonical` tag, which helps prevent duplicate content issues. A full check requires comparing content across multiple URLs, which is beyond the scope of this basic parser."
            )

st.markdown("---")
st.caption("Disclaimer: This tool mixes validated HTML checks with heuristic SEO signals. Use the score as a guide, not a substitute for manual review or rendered-page testing.")
