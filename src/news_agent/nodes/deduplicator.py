"""Deduplication node to ensure unique sources and avoid repeating news."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..models import AgentState, NewsItem


HISTORY_FILE = "processed_urls.json"


def load_history_from_file(output_dir: str) -> set[str]:
    """Load previously processed URLs from local history file."""
    history_path = Path(output_dir) / HISTORY_FILE
    if not history_path.exists():
        return set()

    try:
        with open(history_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Only keep URLs from the last 7 days to prevent unbounded growth
            cutoff = datetime.now().timestamp() - (7 * 24 * 60 * 60)
            return {
                url for url, timestamp in data.items()
                if timestamp > cutoff
            }
    except (json.JSONDecodeError, KeyError):
        return set()


def load_history_from_feishu() -> set[str]:
    """Load previously processed URLs from Feishu Base."""
    try:
        from .feishu_exporter import fetch_existing_urls_from_feishu
        return fetch_existing_urls_from_feishu()
    except Exception as e:
        print(f"⚠️  Failed to load history from Feishu: {e}")
        return set()


def load_history(output_dir: str, use_feishu: bool = False) -> set[str]:
    """Load previously processed URLs.
    
    Args:
        output_dir: Directory for local history file
        use_feishu: If True, load from Feishu Base instead of local file
    """
    if use_feishu:
        return load_history_from_feishu()
    return load_history_from_file(output_dir)


def save_history(output_dir: str, urls: set[str]) -> None:
    """Save processed URLs to local history file."""
    history_path = Path(output_dir) / HISTORY_FILE
    history_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing history and merge
    existing: dict[str, float] = {}
    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            existing = {}

    # Add new URLs with current timestamp
    now = datetime.now().timestamp()
    for url in urls:
        existing[url] = now

    # Prune old entries (older than 7 days)
    cutoff = now - (7 * 24 * 60 * 60)
    existing = {url: ts for url, ts in existing.items() if ts > cutoff}

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def deduplicate_items(
    items: list[NewsItem],
    seen_urls: set[str],
    history_urls: set[str],
) -> tuple[list[NewsItem], set[str]]:
    """Remove duplicate items and items already in history.

    Returns:
        Tuple of (deduplicated items, new URLs to add to history)
    """
    unique_items: list[NewsItem] = []
    new_urls: set[str] = set()

    for item in items:
        url = item.url

        # Skip if already seen in this run
        if url in seen_urls:
            continue

        # Skip if already processed in previous runs
        if url in history_urls:
            continue

        seen_urls.add(url)
        new_urls.add(url)
        unique_items.append(item)

    return unique_items, new_urls


def deduplicate_all_sources(state: AgentState, use_feishu_history: bool = False, skip_save_history: bool = False) -> dict[str, Any]:
    """Deduplicate news items across all sources and filter out previously seen items.
    
    Args:
        state: Current agent state
        use_feishu_history: If True, fetch history from Feishu Base instead of local file
        skip_save_history: If True, don't save history to local file (used when Feishu is source of truth)
    """
    settings = get_settings()

    # Load history of previously processed URLs
    history_urls = load_history(settings.output_dir, use_feishu=use_feishu_history)

    # Track URLs seen in this run
    seen_urls: set[str] = set()
    all_new_urls: set[str] = set()

    # Deduplicate RSS items
    rss_items, new_rss_urls = deduplicate_items(
        state.rss_items, seen_urls, history_urls
    )
    all_new_urls.update(new_rss_urls)

    # Deduplicate web items
    web_items, new_web_urls = deduplicate_items(
        state.web_items, seen_urls, history_urls
    )
    all_new_urls.update(new_web_urls)

    # Deduplicate social items (X/Twitter & Reddit)
    social_items, new_social_urls = deduplicate_items(
        state.social_items, seen_urls, history_urls
    )
    all_new_urls.update(new_social_urls)

    # Deduplicate newsapi items
    newsapi_items, new_newsapi_urls = deduplicate_items(
        state.newsapi_items, seen_urls, history_urls
    )
    all_new_urls.update(new_newsapi_urls)

    # Save new URLs to local history (skip if using Feishu as source of truth)
    if all_new_urls and not skip_save_history:
        save_history(settings.output_dir, all_new_urls)

    return {
        "rss_items": rss_items,
        "web_items": web_items,
        "social_items": social_items,
        "newsapi_items": newsapi_items,
    }

