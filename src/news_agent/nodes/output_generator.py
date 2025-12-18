"""Markdown output generator node."""

from datetime import datetime
from typing import Any

from ..config import get_sources_config, get_settings
from ..models import AgentState, NewsItem, Sentiment


def get_sentiment_emoji(sentiment: Sentiment) -> str:
    """Get emoji for sentiment."""
    if sentiment == Sentiment.POSITIVE:
        return "🟢"
    elif sentiment == Sentiment.NEGATIVE:
        return "🔴"
    return "🟡"


def format_news_item(item: NewsItem, include_links: bool = True) -> str:
    """Format a single news item as markdown."""
    sentiment_emoji = get_sentiment_emoji(item.sentiment)
    lines = []

    # Title with link
    if include_links and item.url:
        lines.append(f"### [{item.title}]({item.url})")
    else:
        lines.append(f"### {item.title}")

    # Metadata line
    meta_parts = [
        f"**Source:** {item.source_name}",
        f"**Sentiment:** {sentiment_emoji} {item.sentiment.value.capitalize()}",
    ]
    if item.published_at:
        meta_parts.append(f"**Published:** {item.published_at.strftime('%Y-%m-%d %H:%M')}")
    if item.keywords_matched:
        meta_parts.append(f"**Keywords:** {', '.join(item.keywords_matched[:3])}")

    lines.append(" | ".join(meta_parts))
    lines.append("")

    # Summary (from Gemini)
    if item.summary:
        lines.append(f"> {item.summary}")
        lines.append("")

    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def group_items_by_category(items: list[NewsItem]) -> dict[str, list[NewsItem]]:
    """Group news items by category."""
    grouped: dict[str, list[NewsItem]] = {}
    for item in items:
        category = item.category or "general"
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(item)
    return grouped


def generate_markdown_output(state: AgentState) -> dict[str, Any]:
    """Generate markdown output from processed news items."""
    settings = get_settings()
    sources_config = get_sources_config(settings)

    lines = []
    now = datetime.now()

    # Header
    lines.append("# Daily News Report")
    lines.append("")
    lines.append(f"**Generated:** {now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Keywords used
    keywords = state.keywords or sources_config.keywords
    if keywords:
        lines.append(f"**Keywords:** {', '.join(keywords)}")
        lines.append("")

    # Statistics
    total_items = len(state.processed_items)
    positive_count = sum(1 for i in state.processed_items if i.sentiment == Sentiment.POSITIVE)
    negative_count = sum(1 for i in state.processed_items if i.sentiment == Sentiment.NEGATIVE)
    neutral_count = sum(1 for i in state.processed_items if i.sentiment == Sentiment.NEUTRAL)

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total Articles:** {total_items}")
    lines.append(f"- **Positive:** 🟢 {positive_count}")
    lines.append(f"- **Negative:** 🔴 {negative_count}")
    lines.append(f"- **Neutral:** 🟡 {neutral_count}")
    lines.append("")

    # Source breakdown
    source_counts: dict[str, int] = {}
    for item in state.processed_items:
        source_type = item.source_type
        source_counts[source_type] = source_counts.get(source_type, 0) + 1

    lines.append("### Sources")
    lines.append("")
    for source_type, count in source_counts.items():
        lines.append(f"- **{source_type.replace('_', ' ').title()}:** {count} items")
    lines.append("")

    lines.append("---")
    lines.append("")

    # Group items by category
    grouped = group_items_by_category(state.processed_items)

    # Sort categories for consistent output
    # Standard category names (snake_case, displayed as Title Case)
    category_order = [
        "tech_news",       # Tech News
        "research",        # Research
        "company_blog",    # Company Blog
        "tech_community",  # Tech Community
        "social",          # Social
        "developer",       # Developer
        "crowdfunding",    # Crowdfunding
        "news",            # News
        "general",         # General
    ]
    sorted_categories = sorted(
        grouped.keys(),
        key=lambda c: category_order.index(c) if c in category_order else len(category_order),
    )

    include_links = sources_config.output.include_source_links

    for category in sorted_categories:
        items = grouped[category]
        category_title = category.replace("_", " ").title()

        lines.append(f"## {category_title}")
        lines.append("")

        # Sort by sentiment (positive first) then by date if available
        sorted_items = sorted(
            items,
            key=lambda i: (
                0 if i.sentiment == Sentiment.POSITIVE else 1 if i.sentiment == Sentiment.NEUTRAL else 2,
                i.published_at or datetime.min,
            ),
            reverse=True,
        )

        for item in sorted_items:
            lines.append(format_news_item(item, include_links))

    # Errors section (if any)
    if state.errors:
        lines.append("## Processing Notes")
        lines.append("")
        for error in state.errors:
            lines.append(f"- ⚠️ {error}")
        lines.append("")

    markdown_output = "\n".join(lines)

    return {
        "markdown_output": markdown_output,
    }
