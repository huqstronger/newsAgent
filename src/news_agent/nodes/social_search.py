"""Social media search node using Tavily.

Searches X/Twitter and Reddit for content matching keywords.

Follows Tavily best practices:
https://docs.tavily.com/documentation/best-practices/best-practices-search
"""

import re
from datetime import datetime
from typing import Any

from tavily import TavilyClient

from ..config import get_sources_config, get_settings
from ..models import AgentState, NewsItem


def matches_keywords(text: str, keywords: list[str]) -> list[str]:
    """Check if text contains any of the keywords (case-insensitive)."""
    matched = []
    text_lower = text.lower()
    for keyword in keywords:
        if keyword.lower() in text_lower:
            matched.append(keyword)
    return matched


def parse_published_date(date_str: str | None) -> datetime | None:
    """Parse published date from Tavily response."""
    if not date_str:
        return None
    try:
        # Tavily returns dates in ISO format
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def truncate_query(query: str, max_length: int = 400) -> str:
    """Ensure query is under max length (Tavily limit is 400 chars)."""
    if len(query) <= max_length:
        return query
    return query[: max_length - 3] + "..."


def is_profile_or_non_content_page(url: str, title: str) -> bool:
    """Check if URL is a profile page or non-content page that should be filtered.

    Filters out:
    - X/Twitter profile pages (no /status/ in URL)
    - Reddit user profiles (/user/)
    - Reddit subreddit main pages (no /comments/)
    - Generic profile/about pages
    """
    url_lower = url.lower()
    title_lower = title.lower()

    # X/Twitter: Profile pages don't have /status/ in URL
    if "x.com" in url_lower or "twitter.com" in url_lower:
        # Valid tweet URLs contain /status/
        if "/status/" not in url_lower:
            return True
        # Profile page titles often end with "/ X" or "/ Posts / X"
        if title_lower.endswith("/ x") or "/ posts / x" in title_lower:
            return True

    # Reddit: Filter user profiles and subreddit main pages
    if "reddit.com" in url_lower:
        # User profile pages
        if "/user/" in url_lower or "/u/" in url_lower:
            # Unless it's a specific post by the user
            if "/comments/" not in url_lower:
                return True
        # Subreddit main page (no specific post)
        if re.match(r"https?://[^/]+/r/[^/]+/?$", url_lower):
            return True

    # Generic non-content indicators in title
    non_content_patterns = [
        r"\| profile\b",
        r"\| about\b",
        r"^profile:",
        r"^about:",
        r"\(@\w+\)\s*/\s*x$",  # (@username) / X pattern
    ]
    for pattern in non_content_patterns:
        if re.search(pattern, title_lower):
            return True

    return False


def is_meaningful_content(title: str, content: str) -> bool:
    """Check if content appears to be meaningful news/discussion, not just a profile."""
    # Title should have meaningful length
    if len(title) < 10:
        return False

    # Content should have some substance
    if len(content) < 50:
        return False

    # Check for profile-only content patterns
    profile_patterns = [
        r"^\s*profile page",
        r"^\s*bio:",
        r"^\s*follower.* following",
        r"shows? (?:his|her|their) bio",
        r"displays? (?:his|her|their) (?:follower|bio)",
    ]
    content_lower = content.lower()
    for pattern in profile_patterns:
        if re.search(pattern, content_lower):
            return False

    return True


def clean_twitter_content(content: str) -> str:
    """Remove X/Twitter UI noise from scraped content.
    
    Removes: login prompts, trending topics, footer, navigation, etc.
    Keeps: actual post/tweet content.
    """
    lines = content.split('\n')
    cleaned_lines: list[str] = []
    
    # Patterns to filter out (X.com UI elements)
    skip_patterns = [
        r"^Don't miss what's happening",
        r"^People on X are the first to know",
        r"^\[Log in\]",
        r"^\[Sign up\]",
        r"^Sign up now",
        r"^Sign up with",
        r"^Create account",
        r"^New to X\?",
        r"^Trending now",
        r"^Trending in",
        r"^What's happening",
        r"^Terms of Service",
        r"^Privacy Policy",
        r"^Cookie Policy",
        r"^Accessibility",
        r"^Ads info",
        r"^More$",
        r"^© \d{4} X Corp",
        r"^\[Show more\]",
        r"^By signing up",
        r"^\d+[KM]?\s*posts?$",  # "3,462 posts"
        r"^Politics · Trending",
        r"^Sports · Trending",
        r"^Entertainment · Trending",
        r"^\|$",  # Single pipe separators
        r"^Read \d+ replies?$",
        r"^\d+$",  # Just numbers (like view counts)
    ]
    
    # Track if we're in a "trending" or "footer" section to skip
    in_skip_section = False
    skip_section_markers = [
        "Trending now",
        "What's happening", 
        "New to X?",
        "Terms of Service",
    ]
    
    for line in lines:
        line_stripped = line.strip()
        
        # Check if entering skip section
        for marker in skip_section_markers:
            if marker in line_stripped:
                in_skip_section = True
                break
        
        # Skip empty lines in skip section
        if in_skip_section:
            # Check if we hit the end marker (actual content usually starts with specific patterns)
            if line_stripped.startswith("Conversation") or line_stripped.startswith("Post"):
                in_skip_section = False
            continue
        
        # Check against skip patterns
        should_skip = False
        for pattern in skip_patterns:
            if re.match(pattern, line_stripped, re.IGNORECASE):
                should_skip = True
                break
        
        if not should_skip and line_stripped:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines).strip()


def extract_tweet_content(content: str) -> str:
    """Extract just the tweet text from X.com scraped content.
    
    Looks for the actual post content and extracts it.
    """
    # First clean the content
    cleaned = clean_twitter_content(content)
    
    # If content is very short after cleaning, it's probably just UI elements
    if len(cleaned) < 50:
        return ""
    
    # Try to find the main tweet content
    # Usually appears after username patterns like @username
    lines = cleaned.split('\n')
    
    # Look for the post content - usually after the username line
    post_lines: list[str] = []
    capturing = False
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Skip image placeholders
        if line_stripped.startswith("![Image"):
            continue
        
        # Skip link-only lines to profile
        if re.match(r'^\[.*\]\(https://x\.com/\w+\)$', line_stripped):
            continue
            
        # Skip timestamp lines
        if re.match(r'^\[\d+:\d+ [AP]M · \w+ \d+, \d+\]', line_stripped):
            continue
        
        # Skip view/engagement counts
        if re.match(r'^[\d,.]+[KM]?$', line_stripped):
            continue
        if line_stripped in ['Views', 'Quote', 'Conversation']:
            continue
        
        # Actual content
        if line_stripped and len(line_stripped) > 20:
            post_lines.append(line_stripped)
    
    return '\n'.join(post_lines).strip()


def search_social_media(state: AgentState) -> dict[str, Any]:
    """Search social media platforms using Tavily for real-time content.

    Best practices applied:
    - Queries kept under 400 characters
    - Uses search_depth="advanced" for higher relevance
    - Uses topic="news" for news sources (includes published_date)
    - Uses time_range for recent content
    - Uses include_domains to restrict to social platforms
    - Filters results by score for relevance
    - Filters out profile pages and non-content URLs
    - Parses published_date metadata
    """
    settings = get_settings()
    sources_config = get_sources_config(settings)

    if not settings.tavily_api_key:
        return {
            "social_items": [],
            "errors": state.errors + ["TAVILY_API_KEY not configured"],
        }

    social_items: list[NewsItem] = []
    errors: list[str] = []
    keywords = state.keywords or sources_config.keywords
    social_config = sources_config.social_media

    # Initialize Tavily client
    tavily_client = TavilyClient(api_key=settings.tavily_api_key)

    # Build domain filter for social media platforms
    # Best practice: minimize domains in include_domains list
    include_domains = social_config.platforms

    # Build search queries from main keywords (best practice: break into smaller sub-queries)
    # Limit to first 10 keywords to avoid too many API calls
    search_queries: list[str] = [
        truncate_query(keyword) for keyword in keywords[:10]
    ]

    seen_urls: set[str] = set()
    min_score_threshold = 0.3  # Filter low-relevance results

    print(f"🔍 Searching social media for {len(search_queries)} keywords...")
    
    for query in search_queries:
        try:
            # Search Reddit with news topic (Reddit discussions are more news-like)
            reddit_response = tavily_client.search(
                query=query,
                search_depth="advanced",
                topic="news",
                max_results=10,
                include_domains=["reddit.com"],
                time_range="day",
                include_raw_content=True,
            )
            
            # Search X/Twitter with general topic (tweets are short-form, not formal news)
            twitter_response = tavily_client.search(
                query=query,
                search_depth="advanced",
                topic="general",  # Better for short-form social content
                max_results=10,
                include_domains=["x.com", "twitter.com"],
                time_range="day",
                include_raw_content=True,
            )
            
            # Combine results
            all_results = (
                reddit_response.get("results", []) + 
                twitter_response.get("results", [])
            )
            
            response = {"results": all_results}

            for result in response.get("results", []):
                url = result.get("url", "")

                # Skip duplicates
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Filter by score threshold (lower for X.com since tweets score lower)
                score = result.get("score", 0)
                is_twitter = "x.com" in url or "twitter.com" in url
                threshold = 0.2 if is_twitter else min_score_threshold
                if score < threshold:
                    continue

                title = result.get("title", "")
                # Best practice: use raw_content for deeper analysis if available
                raw_content = result.get("raw_content") or result.get("content", "")

                # Filter out profile pages and non-content URLs
                if is_profile_or_non_content_page(url, title):
                    continue

                # For Twitter/X, clean the content to remove UI noise
                if is_twitter:
                    content = extract_tweet_content(raw_content)
                    # Skip if no meaningful content after cleaning
                    if len(content) < 30:
                        continue
                else:
                    content = raw_content
                    # Filter out low-quality/non-meaningful content for non-Twitter
                    if not is_meaningful_content(title, content):
                        continue

                # Check if result matches keywords
                combined_text = f"{title} {content}"
                matched_keywords = matches_keywords(combined_text, keywords)

                if matched_keywords:
                    # Determine source name from URL
                    source_name = "Social Media"
                    if is_twitter:
                        source_name = "X (Twitter)"
                    elif "reddit.com" in url:
                        source_name = "Reddit"

                    # Best practice: parse published_date from news topic
                    published_at = parse_published_date(result.get("published_date"))

                    news_item = NewsItem(
                        title=title,
                        url=url,
                        source_name=source_name,
                        source_type="social_media",
                        content=content[:2000],  # Truncated for display
                        full_content=content,  # Cleaned content
                        keywords_matched=matched_keywords,
                        published_at=published_at,
                        category="social",
                    )
                    social_items.append(news_item)

        except Exception as e:
            errors.append(f"Tavily search error for '{query}': {str(e)}")

    # Sort by score/relevance (most relevant first)
    # Then limit total items
    max_items = sources_config.output.max_items_per_source
    social_items = social_items[:max_items]

    return {
        "social_items": social_items,
        "errors": state.errors + errors,
    }
