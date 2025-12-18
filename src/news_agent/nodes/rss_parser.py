"""RSS feed parser node."""

from datetime import datetime
from typing import Any
import re

import feedparser
import httpx

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


def parse_published_date(entry: dict[str, Any]) -> datetime | None:
    """Parse published date from feed entry."""
    for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
        if date_field in entry and entry[date_field]:
            try:
                import time

                return datetime.fromtimestamp(time.mktime(entry[date_field]))
            except (ValueError, TypeError, OverflowError):
                continue
    return None


def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def parse_rss_feeds(state: AgentState) -> dict[str, Any]:
    """Parse RSS feeds and extract news items matching keywords."""
    settings = get_settings()
    sources_config = get_sources_config(settings)

    rss_items: list[NewsItem] = []
    errors: list[str] = []
    keywords = state.keywords or sources_config.keywords

    for feed_config in sources_config.rss_feeds:
        try:
            # Fetch the feed
            with httpx.Client(timeout=30.0) as client:
                response = client.get(feed_config.url)
                response.raise_for_status()

            # Parse the feed
            feed = feedparser.parse(response.text)

            # Get limit from feed config (defaults to 10)
            limit = getattr(feed_config, 'limit', 10)

            # Sort entries by date (most recent first) if dates are available
            entries = list(feed.entries)
            entries_with_dates = []
            for entry in entries:
                pub_date = parse_published_date(entry)
                entries_with_dates.append((entry, pub_date))
            
            # Sort by date descending (newest first), entries without dates go last
            entries_with_dates.sort(
                key=lambda x: x[1] if x[1] else datetime.min,
                reverse=True
            )
            sorted_entries = [e[0] for e in entries_with_dates]

            # Check if this feed should skip keyword filtering
            is_bambu = "bambulab" in feed_config.url.lower()
            
            for entry in sorted_entries[:limit]:
                title = entry.get("title", "")
                content = entry.get("summary", "") or entry.get("description", "")
                content = clean_html(content)

                # Bambu Lab: no keyword filtering, label as "3D printing"
                if is_bambu:
                    news_item = NewsItem(
                        title=title,
                        url=entry.get("link", ""),
                        source_name=feed_config.name,
                        source_type="rss",
                        content=content[:1000],
                        full_content=content,
                        keywords_matched=["3D printing"],  # Fixed label for Bambu Lab
                        published_at=parse_published_date(entry),
                        category=feed_config.category,
                    )
                    rss_items.append(news_item)
                    continue

                # Check if entry matches keywords
                combined_text = f"{title} {content}"
                matched_keywords = matches_keywords(combined_text, keywords)

                if matched_keywords:
                    news_item = NewsItem(
                        title=title,
                        url=entry.get("link", ""),
                        source_name=feed_config.name,
                        source_type="rss",
                        content=content[:1000],  # Truncated for display
                        full_content=content,  # Full fetched content
                        keywords_matched=matched_keywords,
                        published_at=parse_published_date(entry),
                        category=feed_config.category,
                    )
                    rss_items.append(news_item)

        except httpx.HTTPError as e:
            errors.append(f"HTTP error fetching {feed_config.name}: {str(e)}")
        except Exception as e:
            errors.append(f"Error parsing {feed_config.name}: {str(e)}")

    return {
        "rss_items": rss_items,
        "errors": state.errors + errors,
    }

