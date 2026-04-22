from html import escape

import streamlit as st

from seo_analysis import GOOD_READABILITY_THRESHOLD, MAX_KEYWORDS_TO_SHOW, analyze_url, is_valid_url
from seo_utils import MAX_LIVE_LINK_CHECKS
from seo_audit import run_site_audit
from seo_storage import (
    add_monitor,
    build_single_page_scan_record,
    build_site_audit_scan_record,
    compare_scan_records,
    find_previous_scan,
    get_monitor_status,
    get_monitors,
    get_scan_history,
    save_scan_record,
)

MAX_LINKS_TO_SHOW = 15
SITE_AUDIT_MAX_URLS = 100


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


def render_priority_fixes(issues):
    if not issues:
        return

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


def render_search_preview(preview):
    st.markdown(
        f"""
        <div style="border:1px solid #dfe1e5;border-radius:12px;padding:16px;background:#ffffff;">
            <div style="color:#1a0dab;font-size:22px;line-height:1.3;font-weight:500;">
                {escape(preview["title_display"])}
            </div>
            <div style="color:#188038;font-size:14px;margin-top:4px;">
                {escape(preview["display_url"])}
            </div>
            <div style="color:#4d5156;font-size:14px;margin-top:8px;line-height:1.5;">
                {escape(preview["description_display"])}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Title: {preview['title_length']} chars"
        f"{' (likely truncated)' if preview['title_truncated'] else ''} | "
        f"Description: {preview['description_length']} chars"
        f"{' (likely truncated)' if preview['description_truncated'] else ''}"
    )


def render_social_preview_card(preview, platform_key):
    image_url = preview.get("image")
    if image_url:
        st.image(image_url, use_container_width=True)
    else:
        st.caption("No preview image found.")

    st.markdown(f"**{preview['label']}**")
    if platform_key == "twitter":
        st.caption(f"Card type: `{preview.get('card', 'summary')}`")
    else:
        st.caption(preview.get("site_name") or preview.get("url") or "")
    st.markdown(f"**{preview['title']}**")
    st.write(preview["description"])
    st.caption(preview.get("url") or "")


def render_remediation_plan(plan):
    st.subheader("Ready-To-Use Fixes")
    st.caption("These suggestions are generated from the current page analysis. Review them before publishing.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Suggested Title Tag**")
        st.code(plan["suggested_title"], language="text")
        st.markdown("**Suggested Meta Description**")
        st.code(plan["suggested_meta_description"], language="text")
        st.markdown("**Suggested Primary H1**")
        st.code(plan["suggested_h1"], language="text")
    with col2:
        st.markdown("**Suggested Canonical URL**")
        st.code(plan["suggested_canonical"], language="text")
        st.markdown("**Suggested Schema Type**")
        st.code(plan["suggested_schema_type"], language="text")
        if plan["broken_link_targets"]:
            st.markdown("**Broken Links To Update**")
            for href in plan["broken_link_targets"]:
                st.markdown(f"- `{href}`")

    st.markdown("**Recommended Action List**")
    for item in plan["action_items"]:
        st.markdown(f"- `[{item['severity'].upper()}]` {item['issue']} {item['fix']}")

    st.markdown("**Copy-Ready Meta Tag Snippet**")
    st.code(plan["meta_tags_html"], language="html")

    st.markdown("**Copy-Ready JSON-LD Snippet**")
    st.code(plan["schema_json_ld"], language="json")

    if plan["alt_text_suggestions"]:
        st.markdown("**Suggested Alt Text For Missing Images**")
        alt_rows = [
            {"Image": item["src"], "Suggested Alt Text": item["suggested_alt"]}
            for item in plan["alt_text_suggestions"]
        ]
        st.dataframe(alt_rows, use_container_width=True)

    with st.expander("Implementation Notes"):
        for note in plan["implementation_notes"]:
            st.markdown(f"- {note}")


def render_single_page_results(url_input, results):
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
    remediation_plan = results["remediation_plan"]
    indexability = tech_data["indexability"]
    fetch_strategy = results.get("fetch_strategy", "static")
    render_recommended = results.get("render_recommended", False)

    if url_input.lower() != final_url.lower():
        st.info(f"Note: URL redirected to: {final_url}")

    st.success(f"Analysis Complete for: {final_url}")
    if fetch_strategy == "rendered":
        st.info("Analysis used a rendered DOM snapshot after loading page JavaScript.")
    elif render_recommended:
        st.info("The page looked client-rendered, but the analyzer fell back to static HTML.")

    st.header("🚀 Overall SEO Score")
    st.progress(int(overall_score) / 100)
    st.metric(label="Overall Score", value=f"{overall_score:.1f}%")
    if not indexability["can_be_indexed"]:
        st.error("This URL is currently unlikely to be indexable. The overall score is capped until those blockers are resolved.")
    elif indexability["warnings"]:
        st.warning("This URL has indexability warnings. Search engines may prefer a different URL than the one analyzed.")
    st.markdown("---")

    render_priority_fixes(issues)

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

    tab_meta, tab_content, tab_links, tab_tech, tab_fixes = st.tabs(
        ["🏷️ Meta & Social", "📝 On-Page Content", "🔗 Links", "⚙️ Technical SEO", "🛠️ Fixes"]
    )

    with tab_meta:
        st.subheader("Meta Tag Analysis")
        st.markdown("These tags tell search engines and social media platforms about your page.")

        st.subheader("Search Result Preview")
        st.caption("A quick visual check of how the current title and description may appear in search results.")
        render_search_preview(meta_data["search_preview"])

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
        social_previews = meta_data.get("social_previews", {})
        preview_col_1, preview_col_2 = st.columns(2)
        with preview_col_1:
            render_social_preview_card(social_previews["open_graph"], "open_graph")
        with preview_col_2:
            render_social_preview_card(social_previews["twitter"], "twitter")

        st.markdown("---")
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
            live_status = link_data["live_status"]
            st.subheader("Live Link Check")
            if live_status["checked"]:
                col_live_1, col_live_2, col_live_3 = st.columns(3)
                with col_live_1:
                    display_metric_card("Links Checked", live_status["checked_count"], "info")
                with col_live_2:
                    display_metric_card(
                        "Broken Links",
                        live_status["broken_count"],
                        "bad" if live_status["broken_count"] else "good",
                    )
                with col_live_3:
                    display_metric_card(
                        "Restricted / Rate Limited",
                        live_status["warning_count"],
                        "warning" if live_status["warning_count"] else "good",
                    )
                st.caption(
                    f"Live validation checks a capped sample of up to {MAX_LIVE_LINK_CHECKS} unique HTTP links."
                )
                if live_status["broken_links"]:
                    with st.expander(f"View Broken Links ({live_status['broken_count']})", expanded=False):
                        for item in live_status["broken_links"]:
                            label = item["detail"] or "Request failed"
                            st.markdown(f"- `{item['href']}` ({label})")
                if live_status["warning_links"]:
                    with st.expander(
                        f"View Restricted / Rate-Limited Links ({live_status['warning_count']})",
                        expanded=False,
                    ):
                        for item in live_status["warning_links"]:
                            st.markdown(f"- `{item['href']}` ({item['detail']})")
            else:
                st.info("Live link validation was not enabled for this run.")

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

            indexability_status = "Indexable"
            indexability_icon = "good"
            if not indexability["can_be_indexed"]:
                indexability_status = "Blocked"
                indexability_icon = "bad"
            elif indexability["warnings"]:
                indexability_status = "Needs Review"
                indexability_icon = "warning"
            st.markdown(
                f"**{get_status_icon(indexability_icon)} Indexability:** {indexability_status}"
            )
            if indexability["blockers"]:
                st.caption(f"Blockers: {', '.join(f'`{item}`' for item in indexability['blockers'])}")
            elif indexability["warnings"]:
                st.caption(f"Warnings: {', '.join(f'`{item}`' for item in indexability['warnings'])}")

            lt_status = tech_data["load_time_status"]
            lt_text = f"{tech_data['load_time']:.2f} seconds" if tech_data["load_time"] is not None else "Error"
            lt_desc = "Good" if lt_status == "good" else ("Okay" if lt_status == "warning" else ("Slow" if lt_status == "bad" else "Error"))
            st.markdown(f"**{get_status_icon(lt_status)} Server Fetch Time:** {lt_text} ({lt_desc})")
            st.caption("This is a server-side fetch measurement, not a Core Web Vitals or real-user performance metric.")

            performance_hints = tech_data["performance_hints"]
            st.markdown(
                f"**{get_status_icon(performance_hints['status'])} Page Health Snapshot:** "
                f"{performance_hints['html_size_kb']:.1f} KB HTML, "
                f"{performance_hints['dom_elements']} DOM elements, "
                f"{performance_hints['script_count']} external scripts"
            )
            for note in performance_hints["notes"]:
                st.caption(note)

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

            resource_rows = [{
                "HTML Size (KB)": tech_data["performance_hints"]["html_size_kb"],
                "Transfer Size (KB)": tech_data["performance_hints"]["transfer_size_kb"] or "",
                "DOM Elements": tech_data["performance_hints"]["dom_elements"],
                "External Scripts": tech_data["performance_hints"]["script_count"],
                "Stylesheets": tech_data["performance_hints"]["stylesheet_count"],
                "Images": tech_data["performance_hints"]["image_count"],
            }]
            st.dataframe(resource_rows, use_container_width=True)

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

    with tab_fixes:
        render_remediation_plan(remediation_plan)


def render_duplicate_section(label, groups):
    st.subheader(label)
    if not groups:
        st.success("No duplicates detected in this batch.")
        return

    for group in groups[:10]:
        st.markdown(f"**Used on {group['count']} pages:** `{group['value']}`")
        for url in group["urls"][:5]:
            st.markdown(f"- `{url}`")
        if group["count"] > 5:
            st.caption(f"...and {group['count'] - 5} more")


def render_comparison_panel(record, comparison):
    st.subheader("History & Regression Check")
    st.caption(f"Snapshot saved at `{record['created_at']}`")
    if comparison is None:
        st.info("This is the first saved snapshot for this target. Run it again later to compare changes.")
        return

    if comparison["has_regressions"]:
        st.warning("Compared with the previous saved scan, this target has measurable regressions.")
    else:
        st.success("Compared with the previous saved scan, no regressions were detected.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Average Score Delta", f"{comparison['average_score_delta']:+.1f}")
    with col2:
        st.metric("Non-Indexable Delta", f"{comparison['non_indexable_delta']:+d}")
    with col3:
        st.metric("Coverage Delta", f"{comparison['pages_analyzed_delta']:+d}")

    if comparison["newly_non_indexable"]:
        st.markdown("**Newly Non-Indexable URLs**")
        for url in comparison["newly_non_indexable"][:10]:
            st.markdown(f"- `{url}`")

    if comparison["score_drops"]:
        st.markdown("**Largest Score Drops**")
        for item in comparison["score_drops"]:
            st.markdown(f"- `{item['url']}` ({item['delta']:+.1f})")

    if comparison["missing_field_regressions"]:
        st.markdown("**New Missing Metadata**")
        for field, urls in comparison["missing_field_regressions"].items():
            st.markdown(f"- {field.replace('_', ' ').title()}: {len(urls)} new page(s)")

    duplicate_regressions = {key: value for key, value in comparison["duplicate_delta"].items() if value > 0}
    if duplicate_regressions:
        st.markdown("**Duplicate Signal Increases**")
        for key, value in duplicate_regressions.items():
            st.markdown(f"- {key.title()}: +{value}")


def render_monitor_action(record):
    monitor_name = record["target"]
    existing_keys = {monitor["target_key"] for monitor in get_monitors()}
    if record["target_key"] in existing_keys:
        st.caption("This target is already in the monitoring watchlist.")
        return

    if st.button("Add Current Target To Monitoring Watchlist", key=f"watch_{record['id']}"):
        add_monitor(
            monitor_name,
            record["scan_kind"],
            record["target"],
            record["config"],
        )
        st.success("Saved to monitoring watchlist.")


def render_sidebar():
    with st.sidebar:
        st.subheader("Saved Scans")
        history = get_scan_history(limit=8)
        if history:
            for scan in history:
                summary = scan["summary"]
                st.markdown(
                    f"**{scan['scan_kind'].replace('_', ' ').title()}**  \n"
                    f"`{scan['target']}`  \n"
                    f"Score: `{summary['average_score']:.1f}` | Pages: `{summary['pages_analyzed']}`"
                )
        else:
            st.caption("No saved scans yet.")

        st.markdown("---")
        st.subheader("Monitoring")
        monitors = get_monitors()
        if not monitors:
            st.caption("No monitored targets yet.")
            return

        for monitor in monitors[:8]:
            status = get_monitor_status(monitor)
            state_label = {
                "no-data": "No data",
                "baseline": "Baseline only",
                "stable": "Stable",
                "regression": "Regression",
            }[status["state"]]
            state_icon = {
                "no-data": "ℹ️",
                "baseline": "ℹ️",
                "stable": "✅",
                "regression": "⚠️",
            }[status["state"]]
            st.markdown(f"**{state_icon} {monitor['name']}**  \n`{state_label}`")
            if status["latest_scan"]:
                latest = status["latest_scan"]["summary"]
                st.caption(
                    f"Latest score {latest['average_score']:.1f} across {latest['pages_analyzed']} page(s)."
                )


def persist_scan(record, payload_key, payload):
    previous = find_previous_scan(record)
    save_scan_record(record)
    comparison = compare_scan_records(record, previous)
    st.session_state[f"{payload_key}_record"] = record
    st.session_state[f"{payload_key}_comparison"] = comparison
    st.session_state[payload_key] = payload


def render_site_audit_results(report):
    for warning in report["warnings"]:
        st.warning(warning)

    pages = report["pages"]
    summary = report["summary"]
    source_label = "sitemap" if report["source"] == "sitemap" else "internal crawl"

    st.success(f"Site audit complete for {report['target']} using {source_label} discovery.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Pages Analyzed", summary["pages_analyzed"])
    with col2:
        st.metric("Average Score", f"{summary['average_score']:.1f}%")
    with col3:
        st.metric("Non-Indexable Pages", summary["non_indexable_pages"])
    with col4:
        st.metric("Pages With Fetch Errors", summary["pages_with_errors"])

    st.markdown("---")
    top_issues = [
        {
            "category": "audit",
            "severity": "high" if item["count"] >= max(2, summary["pages_analyzed"] // 3 or 1) else "medium",
            "message": item["message"],
            "recommendation": f"Found on {item['count']} page(s) in this audit.",
        }
        for item in summary["top_issues"]
    ]
    render_priority_fixes(top_issues)

    st.subheader("Coverage by Page Type")
    if summary["page_type_counts"]:
        page_type_rows = [
            {"Page Type": page_type.replace("_", " ").title(), "Count": count}
            for page_type, count in sorted(summary["page_type_counts"].items())
        ]
        st.dataframe(page_type_rows, use_container_width=True)
    else:
        st.info("No analyzable pages were found.")

    tab_pages, tab_templates, tab_duplicates = st.tabs(
        ["📄 Pages", "🧩 Templates & Gaps", "🪞 Duplicate Signals"]
    )

    with tab_pages:
        page_rows = [
            {
                "URL": page["final_url"],
                "Page Type": page["page_type"].replace("_", " ").title(),
                "Score": page["overall_score"],
                "Indexable": "Yes" if page["indexable"] else "No",
                "High Issues": page["high_issue_count"],
                "Medium Issues": page["medium_issue_count"],
                "Word Count": page["word_count"],
                "Fetch Error": page["fetch_error"] or "",
            }
            for page in pages
        ]
        st.dataframe(page_rows, use_container_width=True)

        st.subheader("Lowest Scoring Pages")
        if summary["lowest_scoring_pages"]:
            lowest_rows = [
                {
                    "URL": page["final_url"],
                    "Score": page["overall_score"],
                    "High Issues": page["high_issue_count"],
                    "Medium Issues": page["medium_issue_count"],
                    "Title": page["title"] or "",
                }
                for page in summary["lowest_scoring_pages"]
            ]
            st.dataframe(lowest_rows, use_container_width=True)
        else:
            st.info("No page-level audit results to show.")

    with tab_templates:
        st.subheader("Missing Metadata by Field")
        missing_rows = [
            {"Field": field.replace("_", " ").title(), "Missing On Pages": len(urls)}
            for field, urls in summary["missing_by_field"].items()
        ]
        st.dataframe(missing_rows, use_container_width=True)

        for field, urls in summary["missing_by_field"].items():
            if urls:
                with st.expander(f"Pages Missing {field.replace('_', ' ').title()} ({len(urls)})"):
                    for url in urls[:20]:
                        st.markdown(f"- `{url}`")
                    if len(urls) > 20:
                        st.caption(f"...and {len(urls) - 20} more")

        st.subheader("Top Issues by Page Type")
        if summary["issues_by_page_type"]:
            for page_type, issues in summary["issues_by_page_type"].items():
                st.markdown(f"**{page_type.replace('_', ' ').title()}**")
                issue_rows = [{"Issue": issue["message"], "Count": issue["count"]} for issue in issues]
                st.dataframe(issue_rows, use_container_width=True)
        else:
            st.info("No template-level issue patterns detected.")

    with tab_duplicates:
        render_duplicate_section("Duplicate Titles", summary["duplicate_titles"])
        render_duplicate_section("Duplicate Meta Descriptions", summary["duplicate_descriptions"])
        render_duplicate_section("Duplicate Primary H1s", summary["duplicate_h1s"])


st.set_page_config(page_title="Comprehensive SEO Parser", layout="wide", initial_sidebar_state="collapsed")
render_sidebar()

st.title("📊 Comprehensive SEO Parser")
st.markdown("Analyze a single page or audit a batch of URLs from the same site.")

scope = st.radio(
    "Analysis Scope",
    options=["Single Page", "Site Audit"],
    horizontal=True,
)

analysis_mode = st.selectbox(
    "Analysis Mode",
    options=[
        ("auto", "Auto (upgrade to rendered DOM when the page looks client-rendered)"),
        ("static", "Static HTML only"),
        ("rendered", "Rendered page (JavaScript-enabled)"),
    ],
    format_func=lambda item: item[1],
    key="analysis_mode",
)

if scope == "Single Page":
    url_input = st.text_input("Enter URL (e.g., https://www.example.com):", key="url_input")
    validate_live_links = st.checkbox(
        "Enable live broken-link checks",
        value=True,
        help=f"Checks up to {MAX_LIVE_LINK_CHECKS} unique HTTP links. Slower, but more realistic than a static-only audit.",
    )
    if st.button("Analyze URL", key="analyze_button"):
        if not url_input:
            st.warning("Please enter a URL.")
        elif not is_valid_url(url_input):
            st.error("Invalid URL format. Please include 'http://' or 'https://'.")
        else:
            with st.spinner(f"Fetching and analyzing {url_input}... This may take a moment."):
                results = analyze_url(
                    url_input,
                    fetch_mode=analysis_mode[0],
                    validate_live_links=validate_live_links,
                )

            if results["fetch_error"]:
                st.error(results["fetch_error"])
                st.stop()

            record = build_single_page_scan_record(
                url_input,
                results,
                analysis_mode[0],
                validate_live_links=validate_live_links,
            )
            persist_scan(record, "single_results", results)

    if st.session_state.get("single_results"):
        render_comparison_panel(
            st.session_state["single_results_record"],
            st.session_state["single_results_comparison"],
        )
        render_monitor_action(st.session_state["single_results_record"])
        render_single_page_results(url_input or st.session_state["single_results_record"]["target"], st.session_state["single_results"])
else:
    audit_target = st.text_input(
        "Enter a homepage, section URL, or sitemap URL:",
        key="audit_target",
        help="Auto mode tries sitemap discovery first, then falls back to crawling internal links.",
    )
    discovery_mode = st.selectbox(
        "URL Discovery",
        options=[
            ("auto", "Auto (sitemap first, then crawl)"),
            ("sitemap", "Sitemap only"),
            ("crawl", "Internal link crawl only"),
        ],
        format_func=lambda item: item[1],
        key="discovery_mode",
    )
    max_urls = st.slider("Maximum URLs to analyze", min_value=5, max_value=SITE_AUDIT_MAX_URLS, value=25, step=5)

    if st.button("Run Site Audit", key="audit_button"):
        if not audit_target:
            st.warning("Please enter a URL.")
        elif not is_valid_url(audit_target):
            st.error("Invalid URL format. Please include 'http://' or 'https://'.")
        else:
            with st.spinner(f"Running a site audit for {audit_target}... This may take several moments."):
                report = run_site_audit(
                    audit_target,
                    discovery_mode=discovery_mode[0],
                    max_urls=max_urls,
                    fetch_mode=analysis_mode[0],
                )
            record = build_site_audit_scan_record(report)
            persist_scan(record, "site_report", report)

    if st.session_state.get("site_report"):
        render_comparison_panel(
            st.session_state["site_report_record"],
            st.session_state["site_report_comparison"],
        )
        render_monitor_action(st.session_state["site_report_record"])
        render_site_audit_results(st.session_state["site_report"])

st.markdown("---")
st.caption("Disclaimer: This tool mixes validated HTML checks with heuristic SEO signals. Use the score as a guide, not a substitute for manual review or rendered-page testing.")
