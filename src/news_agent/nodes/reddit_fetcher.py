"""Reddit fetcher node using PRAW (Python Reddit API Wrapper).

Fetches latest posts from specified subreddits matching keywords.
See: https://praw.readthedocs.io/en/stable/getting_started/quick_start.html
"""

import os
from datetime import datetime, timezone

import praw
from praw.models import Submission

from ..config import get_sources_config, get_settings
from ..models import AgentState, NewsItem


def get_reddit_client() -> praw.Reddit | None:
    """Create a read-only Reddit instance using PRAW.
    
    Uses Application-Only (Client Credentials) flow for read-only access.
    See: https://praw.readthedocs.io/en/stable/getting_started/authentication.html
    
    Requires environment variables:
    - REDDIT_CLIENT_ID
    - REDDIT_CLIENT_SECRET
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    
    if not client_id or not client_secret:
        print("⚠️  Reddit credentials not configured (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)")
        print("   Get credentials at: https://www.reddit.com/prefs/apps")
        print("   Create a 'script' type app, then set:")
        print("   - REDDIT_CLIENT_ID: the string under 'personal use script'")
        print("   - REDDIT_CLIENT_SECRET: the 'secret' value")
        return None
    
    try:
        # Read-only mode using Application-Only (Client Credentials) flow
        # No username/password needed - just client_id and client_secret
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="newsAgent:v1.0.0 (by /u/newsagent_bot)",
        )
        # Explicitly enable read-only mode
        reddit.read_only = True
        
        # Quick test to verify credentials work
        _ = reddit.subreddit("test")
        
        return reddit
    except Exception as e:
        print(f"⚠️  Failed to create Reddit client: {e}")
        print("   Make sure your REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are correct")
        return None


def matches_keywords(text: str, keywords: list[str]) -> list[str]:
    """Check if text contains any keywords. Returns matched keywords."""
    text_lower = text.lower()
    matched = []
    for keyword in keywords:
        if keyword.lower() in text_lower:
            matched.append(keyword)
    return matched


def submission_to_news_item(
    submission: Submission,
    keywords_matched: list[str],
) -> NewsItem:
    """Convert a PRAW Submission to a NewsItem."""
    # Get submission content
    if submission.is_self:
        content = submission.selftext[:2000] if submission.selftext else ""
    else:
        content = f"Link: {submission.url}"
    
    # Format the full content with metadata
    full_content = f"""# {submission.title}

**Subreddit:** r/{submission.subreddit.display_name}
**Author:** u/{submission.author.name if submission.author else '[deleted]'}
**Score:** {submission.score} | **Comments:** {submission.num_comments}
**Posted:** {datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

{submission.selftext if submission.is_self else f'Link: {submission.url}'}
"""
    
    return NewsItem(
        title=submission.title,
        url=f"https://reddit.com{submission.permalink}",
        source_name=f"r/{submission.subreddit.display_name}",
        source_type="reddit",
        content=content,
        full_content=full_content,
        keywords_matched=keywords_matched,
        published_at=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
        category="social",
    )


def fetch_reddit_posts(state: AgentState) -> dict:
    """Fetch latest Reddit posts from configured subreddits matching keywords.
    
    Uses PRAW to get posts from subreddits like:
    - r/MachineLearning
    - r/artificial
    - r/LocalLLaMA
    - r/singularity
    - etc.
    """
    sources_config = get_sources_config()
    settings = get_settings()
    
    # Get keywords from state or config
    keywords = state.keywords if state.keywords else sources_config.keywords
    
    reddit_items: list[NewsItem] = []
    errors: list[str] = state.errors.copy() if state.errors else []
    
    # Get Reddit client
    reddit = get_reddit_client()
    if not reddit:
        errors.append("Reddit client not available - check credentials")
        return {"reddit_items": reddit_items, "errors": errors}
    
    # Default subreddits for AI/tech news
    subreddits = [
        "MachineLearning",
        "artificial", 
        "LocalLLaMA",
        "singularity",
        "ChatGPT",
        "OpenAI",
        "StableDiffusion",
        "3Dprinting",
        "lasercutting",
    ]
    
    # Get from config if available
    social_config = sources_config.social_media
    if social_config and hasattr(social_config, 'subreddits'):
        subreddits = social_config.subreddits
    
    print(f"📱 Fetching Reddit posts from {len(subreddits)} subreddits...")
    
    seen_urls: set[str] = set()
    
    for subreddit_name in subreddits:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            
            # Get hot and new posts
            for submission in subreddit.hot(limit=10):
                if submission.stickied:
                    continue  # Skip pinned posts
                    
                url = f"https://reddit.com{submission.permalink}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                
                # Check for keyword matches
                search_text = f"{submission.title} {submission.selftext if submission.is_self else ''}"
                matched_keywords = matches_keywords(search_text, keywords)
                
                if matched_keywords:
                    news_item = submission_to_news_item(submission, matched_keywords)
                    reddit_items.append(news_item)
                    print(f"  ✅ r/{subreddit_name}: {submission.title[:50]}...")
                    
        except Exception as e:
            error_msg = f"Error fetching r/{subreddit_name}: {e}"
            print(f"  ⚠️  {error_msg}")
            errors.append(error_msg)
    
    print(f"📱 Reddit: Found {len(reddit_items)} matching posts")
    
    return {
        "reddit_items": reddit_items,
        "errors": errors,
    }

