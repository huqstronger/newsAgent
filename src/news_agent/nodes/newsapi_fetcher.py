"""NewsAPI fetcher node."""

from datetime import datetime, timedelta
from typing import Any

from newsapi import NewsApiClient
from newsapi.newsapi_exception import NewsAPIException

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
    """Parse published date from NewsAPI response."""
    if not date_str:
        return None
    try:
        # NewsAPI returns dates in ISO format
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def fetch_newsapi(state: AgentState) -> dict[str, Any]:
    """Fetch news articles from NewsAPI.

    NewsAPI provides access to headlines and articles from major news sources.
    https://newsapi.org/
    """
    settings = get_settings()
    sources_config = get_sources_config(settings)

    if not settings.newsapi_api_key:
        return {
            "newsapi_items": [],
            "errors": state.errors + ["NEWSAPI_API_KEY not configured"],
        }

    newsapi_items: list[NewsItem] = []
    errors: list[str] = []
    keywords = state.keywords or sources_config.keywords

    # Initialize NewsAPI client
    newsapi = NewsApiClient(api_key=settings.newsapi_api_key)

    # Calculate date range (last 24 hours for daily agent)
    to_date = datetime.now()
    from_date = to_date - timedelta(days=1)

    seen_urls: set[str] = set()

    # Search for each keyword
    for keyword in keywords[:5]:  # Limit to avoid too many API calls
        try:
            # Search everything endpoint for comprehensive results
            response = newsapi.get_everything(
                q=keyword,
                from_param=from_date.strftime("%Y-%m-%d"),
                to=to_date.strftime("%Y-%m-%d"),
                language="en",
                sort_by="publishedAt",
                page_size=10,
            )

            if response.get("status") != "ok":
                errors.append(f"NewsAPI error for '{keyword}': {response.get('message', 'Unknown error')}")
                continue

            for article in response.get("articles", []):
                url = article.get("url", "")

                # Skip duplicates
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = article.get("title", "")
                description = article.get("description", "") or ""
                content = article.get("content", "") or ""

                # Combine description and content for full content
                full_content = f"{description}\n\n{content}" if content else description

                # Check if article matches keywords (should match since we searched for it)
                combined_text = f"{title} {description} {content}"
                matched_keywords = matches_keywords(combined_text, keywords)

                if matched_keywords and title:
                    # Get source name
                    source = article.get("source", {})
                    source_name = source.get("name", "NewsAPI")

                    news_item = NewsItem(
                        title=title,
                        url=url,
                        source_name=f"NewsAPI: {source_name}",
                        source_type="newsapi",
                        content=description[:1000] if description else "",
                        full_content=full_content,
                        keywords_matched=matched_keywords,
                        published_at=parse_published_date(article.get("publishedAt")),
                        category="news",
                    )
                    newsapi_items.append(news_item)

        except NewsAPIException as e:
            errors.append(f"NewsAPI error for '{keyword}': {str(e)}")
        except Exception as e:
            errors.append(f"Error fetching NewsAPI for '{keyword}': {str(e)}")

    # Limit total items
    max_items = sources_config.output.max_items_per_source
    newsapi_items = newsapi_items[:max_items]

    return {
        "newsapi_items": newsapi_items,
        "errors": state.errors + errors,
    }

