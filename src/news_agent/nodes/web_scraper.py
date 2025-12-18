"""Web page scraper node using Firecrawl."""

from typing import Any
import re

from firecrawl import Firecrawl

from ..config import get_sources_config, get_settings
from ..models import AgentState, NewsItem


def matches_keywords(text: str, keywords: list[str]) -> list[str]:
    """Check if text contains any of the keywords (case-insensitive, word boundary for short keywords)."""
    matched = []
    text_lower = text.lower()
    for keyword in keywords:
        keyword_lower = keyword.lower()
        # For short keywords (<=3 chars like "AI"), use word boundary matching
        # to avoid false positives like "tailored" matching "AI"
        if len(keyword) <= 3:
            # Use word boundary regex
            pattern = r'\b' + re.escape(keyword_lower) + r'\b'
            if re.search(pattern, text_lower):
                matched.append(keyword)
        else:
            # For longer keywords, simple substring match is fine
            if keyword_lower in text_lower:
                matched.append(keyword)
    return matched


def extract_title_from_markdown(markdown: str) -> str:
    """Extract title from markdown content (first h1 or h2)."""
    lines = markdown.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("## "):
            return line[3:].strip()
    # Fallback: first non-empty line
    for line in lines:
        if line.strip():
            return line.strip()[:100]
    return "Untitled"


def split_markdown_into_sections(markdown: str, limit: int = 5) -> list[dict[str, str]]:
    """Split markdown into sections based on headings (## or ###) or bold links.
    
    Returns list of dicts with 'title', 'content', and optionally 'url' keys.
    Used to extract individual articles from a blog listing page.
    """
    sections: list[dict[str, str]] = []
    
    # First try: ## or ### headings (common for article titles)
    heading_pattern = r'^(#{2,3})\s+(.+)$'
    
    lines = markdown.split('\n')
    current_section: dict[str, str] | None = None
    content_lines: list[str] = []
    
    for line in lines:
        match = re.match(heading_pattern, line)
        if match:
            # Save previous section
            if current_section is not None:
                current_section['content'] = '\n'.join(content_lines).strip()
                if current_section['content'] or current_section['title']:
                    sections.append(current_section)
                    if len(sections) >= limit:
                        break
            
            # Start new section
            current_section = {
                'title': match.group(2).strip(),
                'content': ''
            }
            content_lines = []
        else:
            content_lines.append(line)
    
    # Don't forget the last section
    if current_section is not None and len(sections) < limit:
        current_section['content'] = '\n'.join(content_lines).strip()
        if current_section['content'] or current_section['title']:
            sections.append(current_section)
    
    # If we found sections with headings, return them
    if sections:
        return sections[:limit]
    
    # Second try: bold links [**Title**](url) - common for blog listings like atomm
    bold_link_pattern = r'\[\*\*([^\]]+)\*\*[^\]]*\]\((https?://[^)]+)\)'
    matches = re.findall(bold_link_pattern, markdown)
    
    if matches:
        seen_urls: set[str] = set()
        for title, url in matches:
            # Deduplicate by URL
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            # Skip navigation/generic titles
            title_clean = title.strip()
            if len(title_clean) < 5:
                continue
            
            # Skip if title looks like category/navigation
            skip_words = ['explore', 'view all', 'see more', 'learn more', 'read more']
            if any(sw in title_clean.lower() for sw in skip_words):
                continue
            
            # Get some context after the link
            content = ""
            escaped_title = re.escape(title)
            link_pattern = rf'\[\*\*{escaped_title}\*\*[^\]]*\]\({re.escape(url)}\)'
            match_obj = re.search(link_pattern, markdown)
            if match_obj:
                context = markdown[match_obj.end():match_obj.end() + 500]
                context_lines = [l.strip() for l in context.split('\n') 
                                if l.strip() 
                                and not l.strip().startswith('[') 
                                and not l.strip().startswith('!')
                                and 'cover' not in l.lower()]
                content = ' '.join(context_lines[:3])[:300]
            
            sections.append({
                'title': title_clean,
                'content': content,
                'url': url
            })
            
            if len(sections) >= limit:
                break
    
    return sections[:limit]


def extract_github_trending(markdown: str, limit: int = 5) -> list[dict[str, str]]:
    """Extract trending repos from GitHub Trending page.
    
    GitHub Trending format: [username / repo](https://github.com/username/repo)
    followed by description text.
    """
    repos: list[dict[str, str]] = []
    
    # Pattern for GitHub repo links with actual repo URL structure
    # Must match: https://github.com/username/reponame (exactly 2 path segments)
    pattern = r'\[([^\]]+)\]\((https://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)\)'
    matches = re.findall(pattern, markdown)
    
    seen_urls: set[str] = set()
    for raw_title, url in matches:
        if len(repos) >= limit:
            break
        
        # Skip non-repo URLs
        if '/trending' in url:
            continue
        if 'spoken_language' in url:
            continue
        if '/sponsors/' in url:
            continue
        if '#' in url:
            continue
        
        # Skip if title is just "Sponsor" or other navigation
        if raw_title.strip().lower() in ('sponsor', 'fork', 'star', 'watch'):
            continue
        
        # Skip duplicate URLs
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        # Extract repo name from URL (most reliable way to get clean title)
        parts = url.rstrip('/').split('/')
        if len(parts) >= 2:
            repo_name = f"{parts[-2]}/{parts[-1]}"
        else:
            # Fallback: clean up the raw title
            title = re.sub(r'\s*/\\+\s*\\*\s*', '/', raw_title).strip()
            title = re.sub(r'\s+', ' ', title)
            repo_name = title
        
        # Get description - look for text after this link
        link_pattern = re.escape(f'[{raw_title}]({url})')
        match_obj = re.search(link_pattern, markdown)
        content = ""
        if match_obj:
            context = markdown[match_obj.end():match_obj.end() + 500]
            # Get first non-link line as description
            for line in context.split('\n'):
                line = line.strip()
                if line and not line.startswith('[') and not line.startswith('!'):
                    content = line[:300]
                    break
        
        repos.append({
            'title': repo_name,
            'content': content,
            'url': url
        })
    
    return repos[:limit]


def extract_atomm_blog_posts(markdown: str, limit: int = 5) -> list[dict[str, str]]:
    """Extract blog posts from atomm.com/blog markdown.
    
    Atomm uses a special format where:
    - Title appears as [**Title**
    - Blog URL appears later as ](https://www.atomm.com/blog/...)
    """
    posts: list[dict[str, str]] = []
    
    # Find blog URLs (excluding generic ones like /blog/3 or /blog/about)
    blog_url_pattern = r'\]\((https://www\.atomm\.com/blog/\d+\-[^)]+)\)'
    url_matches = re.findall(blog_url_pattern, markdown)
    
    if not url_matches:
        return posts
    
    # For each blog URL, find the closest preceding bold title
    for url in url_matches:
        if len(posts) >= limit:
            break
            
        # Find where this URL appears in markdown
        url_idx = markdown.find(url)
        if url_idx < 0:
            continue
        
        # Look for bold title in the text before this URL (within 2000 chars)
        text_before = markdown[max(0, url_idx - 2000):url_idx]
        
        # Find all [**Title** patterns in the text before
        title_pattern = r'\[\*\*([^*\]]+)\*\*'
        title_matches = list(re.finditer(title_pattern, text_before))
        
        if not title_matches:
            continue
        
        # Take the last (closest) title match
        last_title_match = title_matches[-1]
        title = last_title_match.group(1).strip()
        
        # Skip if title is too short or looks like navigation
        if len(title) < 10:
            continue
        skip_words = ['explore', 'view all', 'see more', 'all ']
        if any(sw in title.lower() for sw in skip_words):
            continue
        
        # Extract category and date from context
        context_after_title = text_before[last_title_match.end():]
        content = ""
        
        # Look for category (Announcement, Tutorials) and date
        meta_match = re.search(r'(Announcement|Tutorials)(\d{4}/\d{2}/\d{2})', context_after_title)
        if meta_match:
            content = f"{meta_match.group(1)} - {meta_match.group(2)}"
        
        posts.append({
            'title': title,
            'content': content,
            'url': url
        })
    
    return posts[:limit]


def extract_crowdfunding_projects(markdown: str, source_url: str, limit: int = 5) -> list[dict[str, str]]:
    """Extract individual projects from crowdfunding pages (Kickstarter, Indiegogo).
    
    Projects are identified by their project links and surrounding context.
    """
    projects: list[dict[str, str]] = []
    
    # Patterns for project links
    if "kickstarter.com" in source_url:
        # Kickstarter project links: [Title](https://www.kickstarter.com/projects/...)
        pattern = r'\[([^\]]+)\]\((https://www\.kickstarter\.com/projects/[^)]+)\)'
    elif "indiegogo.com" in source_url:
        # Indiegogo has two formats:
        # 1. Homepage: [Title](https://www.indiegogo.com/en/projects/user/slug)
        # 2. Search results: ### [Title](https://www.indiegogo.com/en/projects/user/slug)
        # Try heading format first (search results), then regular links
        heading_pattern = r'###\s*\[([^\]]+)\]\((https://www\.indiegogo\.com/en/projects/(?!search)[^)]+)\)'
        regular_pattern = r'\[([^\]]+)\]\((https://www\.indiegogo\.com/en/projects/(?!search)[^/]+/[^?\s)]+[^)]*)\)'
        
        # Try heading pattern first (more specific/cleaner titles)
        matches = re.findall(heading_pattern, markdown)
        if not matches:
            matches = re.findall(regular_pattern, markdown)
        
        # Process Indiegogo matches and return early
        seen_urls: set[str] = set()
        for title, url in matches:
            base_url = re.sub(r'\?ref=.*$', '', url)
            if base_url in seen_urls:
                continue
            seen_urls.add(base_url)
            
            title_clean = title.strip()
            if re.match(r'^[\d.,]+[kKmM]?$', title_clean) or len(title_clean) < 5:
                continue
            
            # Get context after the link
            content = ""
            link_pattern = re.escape(f'[{title}]({url})')
            match_obj = re.search(link_pattern, markdown)
            if match_obj:
                context = markdown[match_obj.end():match_obj.end() + 300]
                content_lines = [l.strip() for l in context.split('\n') 
                                if l.strip() and not l.strip().startswith('[') 
                                and not l.strip().startswith('!')]
                content = ' '.join(content_lines[:2])[:200]
            
            projects.append({'title': title_clean, 'content': content, 'url': url})
            if len(projects) >= limit:
                break
        return projects
    else:
        return []
    
    # Find all project links (for Kickstarter)
    matches = re.findall(pattern, markdown)
    seen_urls: set[str] = set()
    
    for title, url in matches:
        # Normalize URL by removing ref/tracking params for deduplication
        base_url = re.sub(r'\?ref=.*$', '', url)
        base_url = re.sub(r'&ref=.*$', '', base_url)
        
        # Skip duplicates
        if base_url in seen_urls:
            continue
        seen_urls.add(base_url)
        
        # Skip generic titles and numeric-only titles (backer counts like "85", "2.3k")
        title_clean = title.strip()
        if title_clean.lower() in ['project we love', 'view project', 'back this project', 'learn more']:
            continue
        # Skip numeric titles (backer counts)
        if re.match(r'^[\d.,]+[kKmM]?$', title_clean):
            continue
        # Skip very short titles
        if len(title_clean) < 5:
            continue
        
        # Find context around this project (description, funding status)
        # Look for text after the link up to the next project or section
        link_pattern = re.escape(f'[{title}]({url})')
        match_obj = re.search(link_pattern, markdown)
        if match_obj:
            # Get text after the link (up to 500 chars)
            start = match_obj.end()
            context = markdown[start:start + 500]
            # Clean up context - get first meaningful paragraph
            context_lines = []
            for line in context.split('\n'):
                line = line.strip()
                if line and not line.startswith('[') and not line.startswith('!'):
                    # Skip image links and other project links
                    if 'funded' in line.lower() or 'days left' in line.lower() or len(line) > 30:
                        context_lines.append(line)
                        if len(context_lines) >= 2:
                            break
            content = ' '.join(context_lines)[:300]
        else:
            content = ""
        
        projects.append({
            'title': title,
            'content': content,
            'url': url,
        })
        
        if len(projects) >= limit:
            break
    
    return projects


def scrape_web_pages(state: AgentState) -> dict[str, Any]:
    """Scrape web pages using Firecrawl and extract news items matching keywords."""
    settings = get_settings()
    sources_config = get_sources_config(settings)

    # Check for Firecrawl API key
    firecrawl_api_key = getattr(settings, "firecrawl_api_key", None)
    if not firecrawl_api_key:
        # Try environment variable
        import os
        firecrawl_api_key = os.environ.get("FIRECRAWL_API_KEY", "")

    if not firecrawl_api_key:
        return {
            "web_items": [],
            "errors": state.errors + ["FIRECRAWL_API_KEY not configured"],
        }

    web_items: list[NewsItem] = []
    errors: list[str] = []
    keywords = state.keywords or sources_config.keywords

    # Initialize Firecrawl client
    firecrawl = Firecrawl(api_key=firecrawl_api_key)

    for page_config in sources_config.web_pages:
        try:
            # Build scrape params using v2 API
            include_tags = None
            if page_config.selector and page_config.selector != "article":
                include_tags = [page_config.selector]

            # Get wait_for from config (for JS-heavy sites)
            wait_for = getattr(page_config, 'wait_for', 0) or None

            # Scrape the page with Firecrawl v2 API
            doc = firecrawl.scrape(
                page_config.url,
                formats=["markdown"],
                only_main_content=True,  # Get only main content, exclude nav/footer
                include_tags=include_tags,
                wait_for=wait_for,  # Wait for JS to load (milliseconds)
            )

            # Get markdown content from Document object
            markdown_content = doc.markdown if hasattr(doc, "markdown") else ""
            if not markdown_content:
                continue

            # Get limit from config (default 5)
            limit = getattr(page_config, 'limit', 5)

            # Check for special site parsers
            is_crowdfunding = page_config.category == "crowdfunding"
            is_atomm = "atomm.com" in page_config.url
            is_github_trending = "github.com/trending" in page_config.url

            # Use special parser for GitHub Trending
            if is_github_trending:
                repos = extract_github_trending(markdown_content, limit)
                for repo in repos:
                    repo_text = f"{repo['title']} {repo['content']}"
                    matched_keywords = matches_keywords(repo_text, keywords)
                    
                    if matched_keywords:
                        news_item = NewsItem(
                            title=repo['title'],
                            url=repo['url'],
                            source_name=page_config.name,
                            source_type="web_page",
                            content=repo['content'][:2000] if repo['content'] else "",
                            full_content=repo['content'],
                            keywords_matched=matched_keywords,
                            published_at=None,
                            category=page_config.category,
                        )
                        web_items.append(news_item)
                continue  # Skip to next page

            # Use special parser for atomm.com blog (no keyword filtering, label as "Laser engraving")
            if is_atomm:
                articles = extract_atomm_blog_posts(markdown_content, limit)
                for article in articles:
                    news_item = NewsItem(
                        title=article['title'],
                        url=article.get('url', page_config.url),
                        source_name=page_config.name,
                        source_type="web_page",
                        content=article['content'][:2000] if article['content'] else "",
                        full_content=article['content'],
                        keywords_matched=["Laser engraving"],  # Fixed label for atomm
                        published_at=None,
                        category=page_config.category,
                    )
                    web_items.append(news_item)
                continue  # Skip to next page

            # Use special parser for crowdfunding sites (with keyword filtering)
            if is_crowdfunding:
                projects = extract_crowdfunding_projects(markdown_content, page_config.url, limit * 2)  # Fetch more, filter later
                for project in projects:
                    # Apply keyword filtering to crowdfunding projects
                    project_text = f"{project['title']} {project['content']}"
                    matched_keywords = matches_keywords(project_text, keywords)
                    
                    if matched_keywords:
                        news_item = NewsItem(
                            title=project['title'],
                            url=project.get('url', page_config.url),
                            source_name=page_config.name,
                            source_type="web_page",
                            content=project['content'][:2000] if project['content'] else "",
                            full_content=project['content'],
                            keywords_matched=matched_keywords,
                            published_at=None,
                            category=page_config.category,
                        )
                        web_items.append(news_item)
                continue  # Skip to next page

            # Try to split into individual articles/sections
            sections = split_markdown_into_sections(markdown_content, limit)

            if sections:
                # Process each section as a separate news item
                for section in sections:
                    section_content = f"## {section['title']}\n\n{section['content']}"
                    clean_content = re.sub(r"\s+", " ", section_content).strip()
                    matched_keywords = matches_keywords(clean_content, keywords)

                    if matched_keywords:
                        # Use section URL if available, otherwise page URL
                        item_url = section.get('url', page_config.url)
                        news_item = NewsItem(
                            title=section['title'] or page_config.name,
                            url=item_url,
                            source_name=page_config.name,
                            source_type="web_page",
                            content=section_content[:2000],
                            full_content=section_content,
                            keywords_matched=matched_keywords,
                            published_at=None,
                            category=page_config.category,
                        )
                        web_items.append(news_item)
            else:
                # Fallback: treat entire page as one item
                title = extract_title_from_markdown(markdown_content) or page_config.name
                clean_content = re.sub(r"\s+", " ", markdown_content).strip()
                matched_keywords = matches_keywords(clean_content, keywords)

                if matched_keywords:
                    news_item = NewsItem(
                        title=title,
                        url=page_config.url,
                        source_name=page_config.name,
                        source_type="web_page",
                        content=markdown_content[:2000],
                        full_content=markdown_content,
                        keywords_matched=matched_keywords,
                        published_at=None,
                        category=page_config.category,
                    )
                    web_items.append(news_item)

        except Exception as e:
            errors.append(f"Firecrawl error for {page_config.name}: {str(e)}")

    return {
        "web_items": web_items,
        "errors": state.errors + errors,
    }
