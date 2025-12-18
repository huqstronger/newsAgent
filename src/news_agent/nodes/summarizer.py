"""Content summarizer and sentiment analyzer using Gemini."""

import os
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..config import get_sources_config, get_settings
from ..models import AgentState, NewsItem, Sentiment


class ContentAnalysis(BaseModel):
    """Structured output for content analysis."""

    summary: str = Field(description="A concise summary of the content")
    sentiment: str = Field(
        description="The sentiment of the content: positive, negative, or neutral"
    )


SYSTEM_PROMPT = """You are a news analyst assistant. Your task is to:
1. Summarize the given news content concisely (max 2-3 sentences)
2. Analyze the sentiment of the content as positive, negative, or neutral

Focus on the key facts and implications. Be objective in your analysis.

Respond with a JSON object containing:
- "summary": A brief summary of the content
- "sentiment": Either "positive", "negative", or "neutral"
"""


def parse_sentiment(sentiment_str: str) -> Sentiment:
    """Parse sentiment string to Sentiment enum."""
    sentiment_lower = sentiment_str.lower().strip()
    if "positive" in sentiment_lower:
        return Sentiment.POSITIVE
    elif "negative" in sentiment_lower:
        return Sentiment.NEGATIVE
    return Sentiment.NEUTRAL


def summarize_and_analyze(state: AgentState) -> dict[str, Any]:
    """Summarize news items and analyze sentiment using Gemini."""
    settings = get_settings()
    sources_config = get_sources_config(settings)

    if not settings.google_api_key:
        return {
            "processed_items": [],
            "errors": state.errors + ["GOOGLE_API_KEY not configured"],
        }

    # Set the API key in environment for langchain
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key

    processed_items: list[NewsItem] = []
    errors: list[str] = []

    # Combine all news items
    all_items = state.rss_items + state.web_items + state.social_items + state.newsapi_items

    # Skip if no items
    if not all_items:
        return {
            "processed_items": [],
            "errors": state.errors,
        }

    # Initialize Gemini model
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.3,
        )
    except Exception as e:
        return {
            "processed_items": all_items,  # Return unsummarized items
            "errors": state.errors + [f"Failed to initialize Gemini: {str(e)}"],
        }

    max_words = sources_config.output.summary_max_words

    for item in all_items:
        try:
            # Prepare the content for analysis
            content_to_analyze = f"Title: {item.title}\n\nContent: {item.content}"

            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=f"Analyze this news content (summary should be max {max_words} words):\n\n{content_to_analyze}"
                ),
            ]

            # Get response from Gemini
            response = llm.invoke(messages)
            response_text = response.content

            # Parse the response
            # Try to extract summary and sentiment from the response
            import json
            import re

            # Try to parse as JSON first
            try:
                # Find JSON in response
                json_match = re.search(r"\{[^}]+\}", response_text, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    summary = analysis.get("summary", response_text[:300])
                    sentiment = parse_sentiment(analysis.get("sentiment", "neutral"))
                else:
                    # Fallback: use response as summary
                    summary = response_text[:300]
                    sentiment = Sentiment.NEUTRAL
            except json.JSONDecodeError:
                summary = response_text[:300]
                sentiment = Sentiment.NEUTRAL

            # Create processed item with summary and sentiment
            processed_item = item.model_copy(
                update={
                    "summary": summary,
                    "sentiment": sentiment,
                }
            )
            processed_items.append(processed_item)

        except Exception as e:
            errors.append(f"Error summarizing '{item.title[:50]}...': {str(e)}")
            # Add item without summary
            processed_items.append(item)

    return {
        "processed_items": processed_items,
        "errors": state.errors + errors,
    }

