"""Data models for News Agent."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


class Sentiment(str, Enum):
    """Sentiment classification for news content."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class NewsItem(BaseModel):
    """A single news item."""

    title: str
    url: str
    source_name: str
    source_type: str  # rss, web_page, social_media
    content: str = ""  # Truncated content for display
    full_content: str = ""  # Full fetched content
    summary: str = ""
    sentiment: Sentiment = Sentiment.NEUTRAL
    keywords_matched: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=datetime.now)
    category: str = "general"


class AgentState(BaseModel):
    """State for the news agent workflow."""

    # Configuration
    keywords: list[str] = Field(default_factory=list)

    # Collected news items from different sources
    rss_items: list[NewsItem] = Field(default_factory=list)
    web_items: list[NewsItem] = Field(default_factory=list)
    social_items: list[NewsItem] = Field(default_factory=list)  # X/Twitter & Reddit via Tavily
    newsapi_items: list[NewsItem] = Field(default_factory=list)

    # Processed items with summaries and sentiment
    processed_items: list[NewsItem] = Field(default_factory=list)

    # Final output
    markdown_output: str = ""

    # Processing status
    errors: list[str] = Field(default_factory=list)
    messages: Annotated[list, add_messages] = Field(default_factory=list)

