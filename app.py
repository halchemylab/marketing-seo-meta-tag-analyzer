import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import time
import re
import json
import textstat # For readability scores
from collections import Counter

# --- Configuration & Constants ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
HEADERS = {'User-Agent': USER_AGENT}
REQUEST_TIMEOUT = 15 # seconds
MIN_CONTENT_LENGTH_WORDS = 300 # Recommended minimum word count
GOOD_LOAD_TIME_THRESHOLD = 2.0 # seconds
OK_LOAD_TIME_THRESHOLD = 4.0 # seconds
GOOD_READABILITY_THRESHOLD = 60 # Flesch Reading Ease score
MAX_KEYWORDS_TO_SHOW = 10
MAX_LINKS_TO_SHOW = 15

# --- Helper Functions ---

def is_valid_url(url):
    """Checks if the URL has a valid format (scheme and domain)."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def fetch_content(url):
    """Fetches HTML content and measures load time."""
    try:
        start_time = time.time()
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        end_time = time.time()
        load_time = end_time - start_time
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        # Check content type to ensure it's likely HTML
        content_type = response.headers.get('content-type', '').lower()
        if 'text/html' not in content_type:
             st.warning(f"Content type is '{content_type}', not 'text/html'. Analysis might be limited.")
             # Allow processing anyway, as sometimes content-type isn't set correctly
             # but raise a warning. If it's truly not HTML, BS4 will likely fail gracefully.

        return response.content, response.url, load_time, None # Return None for error
    except requests.exceptions.Timeout:
        return None, url, None, f"Error: Request timed out after {REQUEST_TIMEOUT} seconds."
    except requests.exceptions.RequestException as e:
        return None, url, None, f"Error fetching URL: {e}"
    except Exception as e:
        return None, url, None, f"An unexpected error occurred during fetch: {e}"

def get_domain(url):
    """Extracts the domain name from a URL."""
    try:
        return urlparse(url).netloc
    except Exception:
        return None

def clean_text(text):
    """Basic text cleaning for keyword analysis."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text) # Keep words, spaces, hyphens
    text = re.sub(r'\s+', ' ', text).strip() # Normalize whitespace
    return text

def get_status_icon(status):
    """Returns an icon based on status ('good', 'warning', 'bad', 'info')."""
    if status == 'good':
        return "✅"
    elif status == 'warning':
        return "⚠️"
    elif status == 'bad':
        return "❌"
    else: # info or neutral
        return "ℹ️"

def display_metric_card(label, value, status='info', help_text=None):
    """Displays a metric with a status icon and optional help text."""
    icon = get_status_icon(status)
    st.metric(label=f"{icon} {label}", value=value, help=help_text)

# --- Analysis Functions ---

def analyze_meta_tags(soup, url):
    """Parses various meta tags."""
    meta_data = {
        'title': None, 'description': None, 'keywords': None, 'robots': None,
        'canonical': None, 'og:title': None, 'og:description': None, 'og:image': None,
        'og:url': None, 'twitter:title': None, 'twitter:description': None,
        'twitter:image': None, 'twitter:card': None, 'viewport': None, 'author': None,
        'charset': None, 'language': None, 'favicon': None, 'alternate': []
    }
    scoring = {'points': 0, 'max_points': 28} # Adjusted max points

    # Title
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        meta_data['title'] = title_tag.string.strip()
        scoring['points'] += 5
    else:
        scoring['points'] += 0 # No points if missing

    # Meta Description
    desc_tag = soup.find('meta', attrs={'name': 'description'})
    if desc_tag and desc_tag.get('content'):
        meta_data['description'] = desc_tag['content'].strip()
        scoring['points'] += 4 # Slightly less critical than title
    else:
         scoring['points'] += 0

    # Meta Keywords (less important nowadays, but check)
    keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
    if keywords_tag and keywords_tag.get('content'):
        meta_data['keywords'] = keywords_tag['content'].strip()
        # No points awarded directly, as it's often ignored by engines
    else:
         scoring['points'] += 0

    # Robots Meta Tag
    robots_tag = soup.find('meta', attrs={'name': 'robots'})
    if robots_tag and robots_tag.get('content'):
        meta_data['robots'] = robots_tag['content'].strip()
        scoring['points'] += 1 # Presence is good practice
    else:
        scoring['points'] += 0 # Assume index, follow if missing

    # Canonical URL
    canonical_tag = soup.find('link', attrs={'rel': 'canonical'})
    if canonical_tag and canonical_tag.get('href'):
        meta_data['canonical'] = urljoin(url, canonical_tag['href'])
        scoring['points'] += 3 # Important for avoiding duplicate content issues
    else:
        scoring['points'] += 0

    # Open Graph Tags
    og_tags = soup.find_all('meta', property=lambda x: x and x.startswith('og:'))
    for tag in og_tags:
        prop = tag.get('property')
        content = tag.get('content')
        if prop and content:
            meta_data[prop] = content.strip()
    if meta_data.get('og:title') and meta_data.get('og:description') and meta_data.get('og:image'):
         scoring['points'] += 3 # Good social sharing setup

    # Twitter Card Tags
    twitter_tags = soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')})
    for tag in twitter_tags:
        name = tag.get('name')
        content = tag.get('content')
        if name and content:
            meta_data[name] = content.strip()
    if meta_data.get('twitter:card') and meta_data.get('twitter:title') and meta_data.get('twitter:description'):
         scoring['points'] += 2 # Good Twitter sharing setup

    # Viewport
    viewport_tag = soup.find('meta', attrs={'name': 'viewport'})
    if viewport_tag and viewport_tag.get('content'):
        meta_data['viewport'] = viewport_tag['content'].strip()
        if 'width=device-width' in meta_data['viewport'] and 'initial-scale=1' in meta_data['viewport']:
            scoring['points'] += 3 # Crucial for mobile-friendliness basic check
        elif 'width=device-width' in meta_data['viewport']:
             scoring['points'] += 1 # Partially good
    else:
        scoring['points'] += 0

    # Author
    author_tag = soup.find('meta', attrs={'name': 'author'})
    if author_tag and author_tag.get('content'):
        meta_data['author'] = author_tag['content'].strip()
        scoring['points'] += 1 # Good practice, adds credibility

    # Charset
    charset_tag = soup.find('meta', charset=True)
    if charset_tag and charset_tag.get('charset'):
        meta_data['charset'] = charset_tag['charset'].strip()
        scoring['points'] += 1 # Important for correct rendering
    else:
        # Check http-equiv as fallback
        http_equiv_tag = soup.find('meta', attrs={'http-equiv': 'Content-Type'})
        if http_equiv_tag and 'charset=' in http_equiv_tag.get('content', ''):
            try:
                meta_data['charset'] = http_equiv_tag['content'].split('charset=')[-1].strip()
                scoring['points'] += 1
            except: pass # Ignore errors here

    # Language
    html_tag = soup.find('html')
    if html_tag and html_tag.get('lang'):
        meta_data['language'] = html_tag['lang'].strip()
        scoring['points'] += 1 # Good for accessibility and targeting

    # Favicon
    favicons = soup.find_all('link', rel=lambda x: x and 'icon' in x.lower())
    if favicons:
        # Prefer specific 'icon' or 'shortcut icon' if available
        preferred_favicon = soup.find('link', rel='icon') or soup.find('link', rel='shortcut icon')
        if preferred_favicon and preferred_favicon.get('href'):
            meta_data['favicon'] = urljoin(url, preferred_favicon['href'])
        elif favicons[0].get('href'): # Fallback to first found
             meta_data['favicon'] = urljoin(url, favicons[0]['href'])

        if meta_data['favicon']:
             scoring['points'] += 1 # Good branding/UX element

    # Alternate links (hreflang)
    alt_tags = soup.find_all('link', attrs={'rel': 'alternate', 'hreflang': True, 'href': True})
    for tag in alt_tags:
        meta_data['alternate'].append({
            'hreflang': tag.get('hreflang'),
            'href': urljoin(url, tag.get('href'))
        })
    if meta_data['alternate']:
        scoring['points'] += 3 # Important for international SEO

    # Calculate final score for this category
    meta_score = (scoring['points'] / scoring['max_points']) * 100 if scoring['max_points'] > 0 else 0

    return meta_data, meta_score

def analyze_on_page_content(soup):
    """Analyzes headings, content length, readability, keywords, and image alts."""
    content_data = {
        'headings': {}, # { 'h1': ['Text1'], 'h2': ['Text2', 'Text3'], ... }
        'word_count': 0,
        'readability_score': None,
        'readability_desc': "Not calculated",
        'top_keywords': [], # List of (keyword, count, density) tuples
        'image_alt_analysis': {'total': 0, 'with_alt': 0, 'missing_alt': 0, 'alt_tags': []},
        'text_content': ""
    }
    scoring = {'points': 0, 'max_points': 30}

    # --- Headings ---
    heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    has_h1 = False
    heading_hierarchy_ok = True # Assume ok initially
    last_level = 0
    for h in heading_tags:
        level = int(h.name[1])
        text = h.get_text(strip=True)
        if not text: # Skip empty headings
            continue

        if h.name not in content_data['headings']:
            content_data['headings'][h.name] = []
        content_data['headings'][h.name].append(text)

        if h.name == 'h1':
            has_h1 = True
        # Basic hierarchy check: level should not jump more than 1 level down
        if level > last_level + 1 and last_level != 0 :
             heading_hierarchy_ok = False # e.g. H1 -> H3 is bad
        last_level = level

    if has_h1:
        scoring['points'] += 5 # Crucial for structure
        if len(content_data['headings'].get('h1', [])) > 1:
             scoring['points'] -= 2 # Penalize multiple H1s slightly
             heading_hierarchy_ok = False # Often considered bad practice
    if heading_hierarchy_ok and has_h1:
        scoring['points'] += 3 # Reward logical structure
    elif has_h1: # Has H1 but bad hierarchy
        scoring['points'] += 1

    # --- Content Extraction (Basic - from body, excluding script/style) ---
    body = soup.find('body')
    if body:
        # Remove script and style elements before getting text
        for element in body(["script", "style", "nav", "footer", "aside"]): # Remove common non-main content areas too
            element.decompose()
        raw_text = body.get_text(separator=' ', strip=True)
        content_data['text_content'] = raw_text
        words = raw_text.split()
        content_data['word_count'] = len(words)
    else:
        content_data['word_count'] = 0
        content_data['text_content'] = ""


    # --- Content Length ---
    if content_data['word_count'] >= MIN_CONTENT_LENGTH_WORDS:
        scoring['points'] += 5 # Reward sufficient content
    elif content_data['word_count'] > 0 :
        scoring['points'] += 2 # Some points for having content

    # --- Readability ---
    if content_data['word_count'] > 50: # Need enough words for meaningful score
        try:
            content_data['readability_score'] = textstat.flesch_reading_ease(content_data['text_content'])
            score = content_data['readability_score']
            if score >= GOOD_READABILITY_THRESHOLD:
                content_data['readability_desc'] = f"Good ({score:.1f} - Fairly easy to read)"
                scoring['points'] += 5
            elif score >= 30:
                content_data['readability_desc'] = f"Okay ({score:.1f} - Plain English)"
                scoring['points'] += 2
            else:
                content_data['readability_desc'] = f"Difficult ({score:.1f} - Very confusing)"
                scoring['points'] += 0
        except Exception as e:
            st.warning(f"Could not calculate readability: {e}")
            content_data['readability_desc'] = "Calculation Error"
    else:
         content_data['readability_desc'] = "Not enough content to calculate"


    # --- Keyword Analysis (Basic) ---
    if content_data['word_count'] > 0:
        cleaned_text = clean_text(content_data['text_content'])
        words = cleaned_text.split()
        # Simple stop word list (can be expanded or use NLTK for better results)
        stop_words = set(["a", "an", "the", "and", "or", "but", "is", "in", "it", "of", "to", "on", "for", "with", "as", "by", "at", "this", "that", "i", "you", "he", "she", "we", "they", "be", "are", "was", "were", "has", "have", "had", "do", "does", "did", "will", "shall", "should", "can", "could", "may", "might", "must", "not", "no", "so", "if", "me", "my", "your", "our", "its", "-", ""])
        meaningful_words = [word for word in words if word not in stop_words and len(word) > 2] # Filter stop words and short words

        if meaningful_words:
            word_counts = Counter(meaningful_words)
            total_meaningful_words = len(meaningful_words)
            for word, count in word_counts.most_common(MAX_KEYWORDS_TO_SHOW):
                density = (count / total_meaningful_words) * 100 if total_meaningful_words > 0 else 0
                content_data['top_keywords'].append((word, count, density))

            if content_data['top_keywords']:
                scoring['points'] += 5 # Reward presence of recurring terms

    # --- Image Alt Tags ---
    images = soup.find_all('img')
    content_data['image_alt_analysis']['total'] = len(images)
    for img in images:
        alt_text = img.get('alt', '').strip()
        src = img.get('src', 'No Source')
        if alt_text:
            content_data['image_alt_analysis']['with_alt'] += 1
            content_data['image_alt_analysis']['alt_tags'].append({'src': src, 'alt': alt_text, 'status': 'present'})
        else:
            content_data['image_alt_analysis']['missing_alt'] += 1
            content_data['image_alt_analysis']['alt_tags'].append({'src': src, 'alt': None, 'status': 'missing'})

    if content_data['image_alt_analysis']['total'] > 0:
        alt_percentage = (content_data['image_alt_analysis']['with_alt'] / content_data['image_alt_analysis']['total']) * 100
        if alt_percentage >= 90:
            scoring['points'] += 4 # Almost all have alts
        elif alt_percentage >= 50:
            scoring['points'] += 2 # More than half have alts
        else:
             scoring['points'] += 0 # Mostly missing
    else:
         scoring['points'] += 4 # No images, no penalty (or reward depending on view)

    content_score = (scoring['points'] / scoring['max_points']) * 100 if scoring['max_points'] > 0 else 0

    return content_data, content_score

def analyze_links(soup, base_url):
    """Analyzes internal, external links, anchor text, and basic broken link check."""
    link_data = {
        'internal': [], 'external': [], 'internal_count': 0, 'external_count': 0,
        'anchor_texts': Counter(), 'links_all': []
    }
    scoring = {'points': 0, 'max_points': 15}
    base_domain = get_domain(base_url)

    links = soup.find_all('a', href=True)

    for link in links:
        href = link['href']
        anchor_text = link.get_text(strip=True)
        full_url = urljoin(base_url, href) # Resolve relative URLs

        # Basic anchor text analysis
        if anchor_text:
             link_data['anchor_texts'][anchor_text] += 1
        else:
             link_data['anchor_texts']['[Empty Anchor]'] += 1

        link_info = {'href': full_url, 'text': anchor_text}

        # Skip invalid URLs or fragments/mailto/tel
        parsed_href = urlparse(full_url)
        if not parsed_href.scheme or parsed_href.scheme not in ['http', 'https']:
            link_info['type'] = 'other'
            link_data['links_all'].append(link_info)
            continue # Skip things like mailto:, tel:, #fragments

        link_domain = get_domain(full_url)

        if link_domain == base_domain:
            link_data['internal'].append(full_url)
            link_data['internal_count'] += 1
            link_info['type'] = 'internal'
        else:
            link_data['external'].append(full_url)
            link_data['external_count'] += 1
            link_info['type'] = 'external'

        link_data['links_all'].append(link_info)

    total_links = link_data['internal_count'] + link_data['external_count']

    if total_links > 0 :
        scoring['points'] += 5 # Basic points for having links

        # Ratio check (simple: reward having both types if total > 5)
        if link_data['internal_count'] > 0 and link_data['external_count'] > 0 and total_links > 5:
            scoring['points'] += 5

        # Anchor text variety (simple: more than 3 unique anchors?)
        if len(link_data['anchor_texts']) > 3 and link_data['anchor_texts']['[Empty Anchor]'] < total_links * 0.5: # Avoid mostly empty anchors
            scoring['points'] += 5
        elif len(link_data['anchor_texts']) > 1:
             scoring['points'] += 2 # Some variety

    link_score = (scoring['points'] / scoring['max_points']) * 100 if scoring['max_points'] > 0 else 0

    return link_data, link_score

def analyze_technical_seo(url, soup, load_time, meta_data):
    """Checks robots.txt, sitemap.xml, load speed, mobile-friendliness, schema."""
    tech_data = {
        'robots_txt': {'status': 'Not Checked', 'content': None, 'url': None},
        'sitemap_xml': {'status': 'Not Checked', 'url': None, 'found_in_robots': False},
        'load_time': load_time, 'load_time_status': 'info',
        'mobile_friendly': {'status': 'Not Checked', 'reason': ''},
        'https_status': 'info',
        'schema_markup': {'present': False, 'types': [], 'details': []}
    }
    scoring = {'points': 0, 'max_points': 27} # Max points adjusted

    parsed_url = urlparse(url)
    base_url_scheme_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

    # --- HTTPS ---
    if parsed_url.scheme == 'https':
        tech_data['https_status'] = 'good'
        scoring['points'] += 3 # Essential nowadays
    else:
        tech_data['https_status'] = 'bad'
        scoring['points'] += 0

    # --- Robots.txt ---
    robots_url = urljoin(base_url_scheme_domain, '/robots.txt')
    tech_data['robots_txt']['url'] = robots_url
    sitemap_directive_found = None
    try:
        robots_res = requests.get(robots_url, headers=HEADERS, timeout=10)
        if robots_res.status_code == 200:
            tech_data['robots_txt']['status'] = 'Found'
            tech_data['robots_txt']['content'] = robots_res.text
            scoring['points'] += 4 # Good to have one
            # Check for Sitemap directive inside robots.txt
            for line in robots_res.text.splitlines():
                if line.strip().lower().startswith('sitemap:'):
                    sitemap_directive_found = line.strip().split(':', 1)[1].strip()
                    tech_data['sitemap_xml']['found_in_robots'] = True
                    tech_data['sitemap_xml']['url'] = sitemap_directive_found # Use this URL first
                    break
        elif robots_res.status_code == 404:
            tech_data['robots_txt']['status'] = 'Not Found'
            scoring['points'] += 0 # Missing is not critical, but not ideal
        else:
            tech_data['robots_txt']['status'] = f"Error (Status: {robots_res.status_code})"
            scoring['points'] += 0
    except requests.exceptions.RequestException as e:
        tech_data['robots_txt']['status'] = f"Error fetching: {e}"
        scoring['points'] += 0

    # --- Sitemap.xml ---
    sitemap_urls_to_check = []
    if sitemap_directive_found:
        sitemap_urls_to_check.append(sitemap_directive_found)
    else:
        # Common locations if not found in robots.txt
        sitemap_urls_to_check.append(urljoin(base_url_scheme_domain, '/sitemap.xml'))
        sitemap_urls_to_check.append(urljoin(base_url_scheme_domain, '/sitemap_index.xml')) # Common alternative

    sitemap_found = False
    for sitemap_url in sitemap_urls_to_check:
         if sitemap_found: break # Stop if found
         tech_data['sitemap_xml']['url'] = sitemap_url # Update url being checked
         try:
             # Use HEAD request for speed, fallback to GET if needed
             sitemap_res = requests.head(sitemap_url, headers=HEADERS, timeout=10, allow_redirects=True)
             if sitemap_res.status_code == 200:
                 tech_data['sitemap_xml']['status'] = 'Found'
                 sitemap_found = True
                 scoring['points'] += 5 # Important for discoverability
                 break
             elif sitemap_res.status_code == 404:
                 tech_data['sitemap_xml']['status'] = 'Not Found' # Continue checking alternatives
             else:
                 # Try GET if HEAD failed for non-404 reasons (e.g., method not allowed)
                 sitemap_res_get = requests.get(sitemap_url, headers=HEADERS, timeout=10, allow_redirects=True)
                 if sitemap_res_get.status_code == 200:
                      tech_data['sitemap_xml']['status'] = 'Found'
                      sitemap_found = True
                      scoring['points'] += 5
                      break
                 elif sitemap_res_get.status_code == 404:
                      tech_data['sitemap_xml']['status'] = 'Not Found'
                 else:
                      tech_data['sitemap_xml']['status'] = f"Error (Status: {sitemap_res_get.status_code})"

         except requests.exceptions.RequestException:
             tech_data['sitemap_xml']['status'] = 'Error Fetching'
             # Don't break here, maybe the next URL works

    if not sitemap_found:
        tech_data['sitemap_xml']['status'] = 'Not Found (Common Locations)'
        scoring['points'] += 0

    # --- Page Load Speed ---
    if load_time is not None:
        if load_time <= GOOD_LOAD_TIME_THRESHOLD:
            tech_data['load_time_status'] = 'good'
            scoring['points'] += 7 # Big impact on UX and SEO
        elif load_time <= OK_LOAD_TIME_THRESHOLD:
            tech_data['load_time_status'] = 'warning'
            scoring['points'] += 3
        else:
            tech_data['load_time_status'] = 'bad'
            scoring['points'] += 0
    else:
         tech_data['load_time_status'] = 'error' # Couldn't measure
         scoring['points'] += 0

    # --- Mobile-Friendliness (Viewport Check) ---
    viewport_content = meta_data.get('viewport')
    if viewport_content:
        if 'width=device-width' in viewport_content and 'initial-scale=1' in viewport_content:
            tech_data['mobile_friendly']['status'] = 'good'
            tech_data['mobile_friendly']['reason'] = 'Viewport tag correctly configured.'
            scoring['points'] += 5 # Crucial factor
        elif 'width=device-width' in viewport_content:
            tech_data['mobile_friendly']['status'] = 'warning'
            tech_data['mobile_friendly']['reason'] = 'Viewport tag found, but might lack `initial-scale=1`.'
            scoring['points'] += 2
        else:
            tech_data['mobile_friendly']['status'] = 'bad'
            tech_data['mobile_friendly']['reason'] = 'Viewport tag present but seems incorrectly configured.'
            scoring['points'] += 0
    else:
        tech_data['mobile_friendly']['status'] = 'bad'
        tech_data['mobile_friendly']['reason'] = 'Viewport meta tag not found.'
        scoring['points'] += 0

    # --- Schema Markup ---
    schema_tags = soup.find_all('script', type='application/ld+json')
    for tag in schema_tags:
        try:
            schema_json = json.loads(tag.string)
            tech_data['schema_markup']['present'] = True
            tech_data['schema_markup']['details'].append(schema_json) # Store parsed schema
            # Extract @type if it exists
            if isinstance(schema_json, dict):
                 schema_type = schema_json.get('@type')
                 if schema_type:
                      tech_data['schema_markup']['types'].append(str(schema_type))
            elif isinstance(schema_json, list): # Handle array of schema objects
                for item in schema_json:
                    if isinstance(item, dict):
                         schema_type = item.get('@type')
                         if schema_type:
                              tech_data['schema_markup']['types'].append(str(schema_type))

        except json.JSONDecodeError:
            # Found the tag, but couldn't parse it
            tech_data['schema_markup']['present'] = True # Still counts as present
            tech_data['schema_markup']['types'].append("Error Parsing")
            st.warning("Found schema tag (application/ld+json) but could not parse its content.")
        except Exception:
             tech_data['schema_markup']['present'] = True # Still counts as present
             tech_data['schema_markup']['types'].append("Error Processing")


    if tech_data['schema_markup']['present']:
        scoring['points'] += 3 # Good for rich snippets

    tech_score = (scoring['points'] / scoring['max_points']) * 100 if scoring['max_points'] > 0 else 0

    return tech_data, tech_score


# --- Streamlit App UI ---

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
            # --- Fetching ---
            html_content, final_url, load_time, fetch_error = fetch_content(url_input)

            if fetch_error:
                st.error(fetch_error)
                st.stop() # Stop execution if fetch failed

            if html_content is None:
                 st.error("Could not retrieve content from the URL.")
                 st.stop()

            # If redirected, show the final URL
            if url_input.lower() != final_url.lower():
                 st.info(f"Note: URL redirected to: {final_url}")

            # --- Parsing ---
            try:
                # Use lxml for potentially faster parsing if installed, fall back to html.parser
                try:
                    soup = BeautifulSoup(html_content, 'lxml')
                except:
                    soup = BeautifulSoup(html_content, 'html.parser')

            except Exception as e:
                 st.error(f"Error parsing HTML content: {e}")
                 st.stop()

            # --- Analysis ---
            try:
                meta_data, meta_score = analyze_meta_tags(soup, final_url)
                content_data, content_score = analyze_on_page_content(soup)
                link_data, link_score = analyze_links(soup, final_url)
                tech_data, tech_score = analyze_technical_seo(final_url, soup, load_time, meta_data)

                # --- Social SEO Score (Derived from Meta Tags) ---
                social_points = 0
                social_max_points = 5 # og:tags + twitter:tags points from meta_score calculation
                if meta_data.get('og:title') and meta_data.get('og:description') and meta_data.get('og:image'):
                    social_points += 3
                if meta_data.get('twitter:card') and meta_data.get('twitter:title') and meta_data.get('twitter:description'):
                     social_points += 2
                social_score = (social_points / social_max_points) * 100 if social_max_points > 0 else 0


                # --- Overall Score Calculation (Weighted Average) ---
                # Weights can be adjusted based on perceived importance
                weights = {'meta': 0.20, 'content': 0.35, 'links': 0.15, 'tech': 0.30}
                overall_score = (meta_score * weights['meta'] +
                                 content_score * weights['content'] +
                                 link_score * weights['links'] +
                                 tech_score * weights['tech'])

            except Exception as e:
                st.error(f"An error occurred during analysis: {e}")
                import traceback
                st.error(traceback.format_exc()) # Show detailed error for debugging if needed
                st.stop()


        # --- Display Results ---
        st.success(f"Analysis Complete for: {final_url}")

        st.header("🚀 Overall SEO Score")
        st.progress(int(overall_score) / 100)
        st.metric(label="Overall Score", value=f"{overall_score:.1f}%")
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

        # --- Detailed Analysis Sections ---
        tab_titles = ["🏷️ Meta & Social", "📝 On-Page Content", "🔗 Links", "⚙️ Technical SEO"]
        tab_meta, tab_content, tab_links, tab_tech = st.tabs(tab_titles)

        # --- Meta Tags Tab ---
        with tab_meta:
            st.subheader("Meta Tag Analysis")
            st.markdown("These tags tell search engines and social media platforms about your page.")

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                 display_metric_card("Title Tag", meta_data.get('title') or "Missing", 'good' if meta_data.get('title') else 'bad', "The main title shown in search results and browser tabs.")
                 display_metric_card("Meta Description", meta_data.get('description') or "Missing", 'good' if meta_data.get('description') else 'warning', "Summary shown below the title in search results.")
                 display_metric_card("Canonical URL", meta_data.get('canonical') or "Missing", 'good' if meta_data.get('canonical') else 'warning', "Specifies the preferred version of this page.")
                 display_metric_card("Robots Meta Tag", meta_data.get('robots') or "Default (index, follow)", 'info' if meta_data.get('robots') else 'info', "Instructions for search engine crawlers (e.g., 'noindex').")
                 display_metric_card("Viewport Tag", meta_data.get('viewport') or "Missing", 'good' if meta_data.get('viewport') and 'width=device-width' in meta_data.get('viewport') else 'bad', "Essential for making the page responsive on mobile devices.")
            with col_m2:
                 display_metric_card("Character Set (Charset)", meta_data.get('charset') or "Not Found", 'good' if meta_data.get('charset') else 'warning', "Ensures text displays correctly (UTF-8 recommended).")
                 display_metric_card("Language", meta_data.get('language') or "Not Specified", 'good' if meta_data.get('language') else 'warning', "Helps search engines understand the page language.")
                 display_metric_card("Favicon", meta_data.get('favicon') or "Missing", 'good' if meta_data.get('favicon') else 'info', "Small icon shown in browser tabs.")
                 display_metric_card("Author", meta_data.get('author') or "Not Specified", 'info', "Specifies the page author (less common).")
                 display_metric_card("Keywords Meta Tag", meta_data.get('keywords') or "Not Found", 'info', "List of keywords (mostly ignored by Google now).")


            st.subheader("Social Media Tags (Open Graph & Twitter)")
            st.markdown("These tags control how your page looks when shared on platforms like Facebook and Twitter.")
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.markdown("**Open Graph (Facebook, LinkedIn, etc.)**")
                display_metric_card("OG Title", meta_data.get('og:title') or "Missing", 'good' if meta_data.get('og:title') else 'warning')
                display_metric_card("OG Description", meta_data.get('og:description') or "Missing", 'good' if meta_data.get('og:description') else 'warning')
                display_metric_card("OG Image", meta_data.get('og:image') or "Missing", 'good' if meta_data.get('og:image') else 'warning')
                display_metric_card("OG URL", meta_data.get('og:url') or "Missing", 'info')
            with col_s2:
                st.markdown("**Twitter Card**")
                display_metric_card("Twitter Card Type", meta_data.get('twitter:card') or "Missing", 'good' if meta_data.get('twitter:card') else 'warning')
                display_metric_card("Twitter Title", meta_data.get('twitter:title') or "Missing", 'good' if meta_data.get('twitter:title') else 'warning')
                display_metric_card("Twitter Description", meta_data.get('twitter:description') or "Missing", 'good' if meta_data.get('twitter:description') else 'warning')
                display_metric_card("Twitter Image", meta_data.get('twitter:image') or "Missing", 'good' if meta_data.get('twitter:image') else 'warning')

            if meta_data.get('alternate'):
                 with st.expander("Alternate Language/Region Links (hreflang)"):
                      st.markdown("Found alternate versions specified for different languages or regions:")
                      for alt in meta_data['alternate']:
                           st.write(f"- **Lang/Region:** `{alt.get('hreflang')}` → **URL:** `{alt.get('href')}`")

        # --- On-Page Content Tab ---
        with tab_content:
            st.subheader("Content Analysis")
            st.markdown("Analyzes the text content, structure, and accessibility elements on the page.")

            col_c1, col_c2 = st.columns(2)
            wc_status = 'good' if content_data['word_count'] >= MIN_CONTENT_LENGTH_WORDS else ('warning' if content_data['word_count'] > 0 else 'bad')
            with col_c1:
                display_metric_card("Word Count", f"{content_data['word_count']} words", wc_status, f"Total words found in the main content area. Recommended: {MIN_CONTENT_LENGTH_WORDS}+")
            with col_c2:
                readability_status = 'info'
                if content_data['readability_score'] is not None:
                     if content_data['readability_score'] >= GOOD_READABILITY_THRESHOLD: readability_status = 'good'
                     elif content_data['readability_score'] >= 30: readability_status = 'warning'
                     else: readability_status = 'bad'
                display_metric_card("Readability (Flesch Score)", content_data['readability_desc'], readability_status, "Score indicating how easy the text is to read. Higher is better (60+ is generally good).")

            st.subheader("Heading Structure (H1-H6)")
            if content_data['headings']:
                h1_count = len(content_data['headings'].get('h1', []))
                if h1_count == 1:
                    st.success(f"{get_status_icon('good')} Found exactly one H1 tag: `{content_data['headings']['h1'][0]}`")
                elif h1_count > 1:
                     st.warning(f"{get_status_icon('warning')} Found {h1_count} H1 tags. Generally, only one H1 per page is recommended.")
                     for h1_text in content_data['headings']['h1']: st.markdown(f" - `{h1_text}`")
                else:
                     st.error(f"{get_status_icon('bad')} No H1 tag found. An H1 tag is crucial for defining the main topic.")

                with st.expander("View All Headings"):
                    for level in range(1, 7):
                        tag = f'h{level}'
                        if tag in content_data['headings']:
                            st.markdown(f"**{tag.upper()} Tags:**")
                            for text in content_data['headings'][tag]:
                                st.markdown(f"- `{text}`")
            else:
                st.warning("No heading tags (H1-H6) found on the page.")

            st.subheader("Keyword Analysis (Top Terms)")
            if content_data['top_keywords']:
                 st.markdown(f"Top {len(content_data['top_keywords'])} keywords found in the content (based on frequency, excludes common stop words):")
                 # Prepare data for a simple table/list
                 kw_data = [{"Keyword": kw[0], "Count": kw[1], "Density (%)": f"{kw[2]:.2f}%"} for kw in content_data['top_keywords']]
                 st.dataframe(kw_data, use_container_width=True)
            else:
                 st.info("No significant keywords could be extracted (or content is very short).")

            st.subheader("Image Alt Text Analysis")
            img_alt = content_data['image_alt_analysis']
            if img_alt['total'] > 0:
                missing_perc = (img_alt['missing_alt'] / img_alt['total']) * 100
                alt_status = 'good' if missing_perc <= 10 else ('warning' if missing_perc <= 50 else 'bad')
                display_metric_card("Images Found", img_alt['total'], 'info')
                display_metric_card("Images Missing Alt Text", f"{img_alt['missing_alt']} ({missing_perc:.1f}%)", alt_status, "Alt text describes images for search engines and visually impaired users. Aim for 0 missing.")

                if img_alt['missing_alt'] > 0:
                     with st.expander(f"View Images Missing Alt Text ({img_alt['missing_alt']})"):
                          missing_alts = [item['src'] for item in img_alt['alt_tags'] if item['status'] == 'missing']
                          for i, src in enumerate(missing_alts):
                               st.markdown(f"- `{src if len(src)<100 else src[:100]+'...'}`") # Show truncated src
                               if i >= MAX_LINKS_TO_SHOW -1 : # Limit display
                                    st.markdown(f"...and {len(missing_alts)-MAX_LINKS_TO_SHOW} more")
                                    break
            else:
                st.info("No images (`<img>` tags) found on the page.")


        # --- Link Analysis Tab ---
        with tab_links:
            st.subheader("Link Analysis")
            st.markdown("Examines the links pointing away from this page.")

            col_l1, col_l2 = st.columns(2)
            with col_l1:
                display_metric_card("Internal Links", link_data['internal_count'], 'info', "Links pointing to other pages on the same website.")
            with col_l2:
                display_metric_card("External Links", link_data['external_count'], 'info', "Links pointing to different websites.")

            total_links = link_data['internal_count'] + link_data['external_count']
            if total_links > 0:
                # Display Internal Links
                with st.expander(f"View Internal Links ({link_data['internal_count']})", expanded=False):
                    if link_data['internal']:
                        for i, link in enumerate(link_data['internal']):
                            st.markdown(f"- `{link}`")
                            if i >= MAX_LINKS_TO_SHOW -1 :
                                st.markdown(f"...and {link_data['internal_count']-MAX_LINKS_TO_SHOW} more")
                                break
                    else:
                        st.markdown("_No internal links found._")

                # Display External Links
                with st.expander(f"View External Links ({link_data['external_count']})", expanded=False):
                     if link_data['external']:
                        for i, link in enumerate(link_data['external']):
                            st.markdown(f"- `{link}`")
                            if i >= MAX_LINKS_TO_SHOW -1 :
                                st.markdown(f"...and {link_data['external_count']-MAX_LINKS_TO_SHOW} more")
                                break
                     else:
                         st.markdown("_No external links found._")

                # Anchor Text Analysis
                st.subheader("Anchor Text Analysis")
                st.markdown("The visible text used for links. Diverse and descriptive anchor text is generally good.")
                if link_data['anchor_texts']:
                    # Show top anchor texts
                    with st.expander(f"View Anchor Text Usage (Top {MAX_KEYWORDS_TO_SHOW})"):
                        anchor_list = [{"Anchor Text": text if text else "[Empty Anchor]", "Count": count} for text, count in link_data['anchor_texts'].most_common(MAX_KEYWORDS_TO_SHOW)]
                        st.dataframe(anchor_list, use_container_width=True)
                        if link_data['anchor_texts']['[Empty Anchor]'] > 0:
                            st.warning(f"{get_status_icon('warning')} Found {link_data['anchor_texts']['[Empty Anchor]']} link(s) with empty or missing anchor text.")
                        common_generic = ["click here", "learn more", "read more", "here"]
                        generic_anchors_found = [text for text in link_data['anchor_texts'] if text.lower() in common_generic]
                        if generic_anchors_found:
                             st.warning(f"{get_status_icon('warning')} Found generic anchor text like: {', '.join(f'`{a}`' for a in generic_anchors_found)}. Use descriptive text instead.")

                else:
                    st.info("No anchor text data to analyze.")

                # Note: Live broken link checking is too slow/complex for this basic tool.
                st.info(f"{get_status_icon('info')} Note: This tool does not perform live checks for broken links due to performance reasons.")

            else:
                st.info("No internal or external links found on the page.")


        # --- Technical SEO Tab ---
        with tab_tech:
            st.subheader("Technical SEO Checks")
            st.markdown("Assesses technical aspects affecting crawlability, indexing, and performance.")

            col_t1, col_t2 = st.columns(2)
            with col_t1:
                 # HTTPS
                 https_status_map = {'good': '✅ Using HTTPS', 'bad': '❌ Not Using HTTPS (Insecure)', 'info': 'ℹ️ Could not determine'}
                 https_icon = get_status_icon(tech_data['https_status'])
                 st.markdown(f"**{https_icon} Security (HTTPS):** {https_status_map.get(tech_data['https_status'], 'Unknown')}")

                 # Load Speed
                 lt_status = tech_data['load_time_status']
                 lt_icon = get_status_icon(lt_status)
                 lt_text = f"{tech_data['load_time']:.2f} seconds" if tech_data['load_time'] is not None else "Error"
                 lt_desc = "Good" if lt_status == 'good' else ("Okay" if lt_status == 'warning' else ("Slow" if lt_status == 'bad' else "Error"))
                 st.markdown(f"**{lt_icon} Page Load Time:** {lt_text} ({lt_desc})")
                 st.caption("Based on server response time. Actual user experience may vary.")

                 # Mobile Friendly (Viewport)
                 mf_status = tech_data['mobile_friendly']['status']
                 mf_icon = get_status_icon(mf_status)
                 mf_text = "Likely Mobile-Friendly" if mf_status == 'good' else ("Potential Issues" if mf_status == 'warning' else "Not Mobile-Friendly")
                 st.markdown(f"**{mf_icon} Mobile-Friendly Check:** {mf_text}")
                 st.caption(f"({tech_data['mobile_friendly']['reason']}) - Based on viewport tag presence.")

            with col_t2:
                 # Robots.txt
                 rb_status = tech_data['robots_txt']['status']
                 rb_icon = get_status_icon('good' if rb_status == 'Found' else ('bad' if rb_status == 'Not Found' else 'warning'))
                 rb_url = tech_data['robots_txt']['url']
                 st.markdown(f"**{rb_icon} robots.txt Status:** {rb_status}")
                 if rb_url: st.caption(f"Checked at: `{rb_url}`")
                 if rb_status == 'Found' and tech_data['robots_txt']['content']:
                      with st.expander("View robots.txt Content"):
                           st.code(tech_data['robots_txt']['content'], language='text')

                 # Sitemap.xml
                 sm_status = tech_data['sitemap_xml']['status']
                 sm_icon = get_status_icon('good' if 'Found' in sm_status else ('bad' if 'Not Found' in sm_status else 'warning'))
                 sm_url = tech_data['sitemap_xml']['url']
                 found_method = "(from robots.txt)" if tech_data['sitemap_xml']['found_in_robots'] else "(common locations)"
                 st.markdown(f"**{sm_icon} sitemap.xml Status:** {sm_status} {found_method}")
                 if sm_url: st.caption(f"Checked: `{sm_url}`")

                 # Schema Markup
                 sc_present = tech_data['schema_markup']['present']
                 sc_icon = get_status_icon('good' if sc_present else 'info')
                 sc_text = "Present" if sc_present else "Not Detected"
                 st.markdown(f"**{sc_icon} Schema Markup (Structured Data):** {sc_text}")
                 if sc_present and tech_data['schema_markup']['types']:
                      unique_types = sorted(list(set(tech_data['schema_markup']['types']))) # Get unique types found
                      st.caption(f"Detected types: {', '.join(f'`{t}`' for t in unique_types)}")
                      # Optionally, show the raw JSON in an expander
                      # with st.expander("View Schema JSON"):
                      #     st.json(tech_data['schema_markup']['details'])

            # Duplicate Content Note
            st.markdown("---")
            st.info(f"{get_status_icon('info')} **Duplicate Content:** This tool checks for a `canonical` tag, which helps prevent duplicate content issues. A full check requires comparing content across multiple URLs, which is beyond the scope of this basic parser.")


# --- Footer/Info ---
st.markdown("---")
st.caption("Disclaimer: This tool provides a basic automated analysis. SEO is complex and requires manual review and strategy. Scores are indicative and based on common best practices.")