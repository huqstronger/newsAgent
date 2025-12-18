"""LangGraph graph export for langgraph dev server."""

from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict, Annotated

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from .models import NewsItem, Sentiment
from .config import get_sources_config, get_settings


class NewsAgentState(TypedDict):
    """State for the news agent workflow."""

    # Configuration
    keywords: list[str]

    # Skip flags - set these to True to skip specific sources
    # Example: {"skip_rss": True, "skip_social": True} to only run web scraping
    skip_rss: bool
    skip_web: bool
    skip_social: bool  # X/Twitter & Reddit via Tavily
    skip_newsapi: bool
    skip_summarize: bool  # Skip AI summarization (faster testing)
    skip_feishu: bool  # Skip Feishu export
    skip_local_output: bool  # Skip saving to local output folder
    use_feishu_history: bool  # Use Feishu Base for deduplication instead of local file

    # Collected news items from different sources
    rss_items: list[NewsItem]
    web_items: list[NewsItem]
    social_items: list[NewsItem]  # X/Twitter & Reddit via Tavily
    newsapi_items: list[NewsItem]

    # Processed items with summaries and sentiment
    processed_items: list[NewsItem]

    # Final output
    markdown_output: str

    # Saved file paths
    output_file: str
    html_file: str
    
    # Feishu export result
    feishu_export: dict

    # Processing status
    errors: list[str]

    # Messages for agent communication
    messages: Annotated[list, add_messages]


def fetch_rss_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Parse RSS feeds and extract news items matching keywords."""
    if state.get("skip_rss", False):
        print("⏭️  Skipping RSS feeds (skip_rss=True)")
        return {"rss_items": []}

    from .nodes.rss_parser import parse_rss_feeds
    from .models import AgentState

    agent_state = AgentState(
        keywords=state.get("keywords", []),
        errors=state.get("errors", []),
    )
    result = parse_rss_feeds(agent_state)
    return {
        "rss_items": result.get("rss_items", []),
        "errors": result.get("errors", []),
    }


def fetch_web_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Scrape web pages for news articles."""
    if state.get("skip_web", False):
        print("⏭️  Skipping web pages (skip_web=True)")
        return {"web_items": []}

    from .nodes.web_scraper import scrape_web_pages
    from .models import AgentState

    agent_state = AgentState(
        keywords=state.get("keywords", []),
        errors=state.get("errors", []),
    )
    result = scrape_web_pages(agent_state)
    return {
        "web_items": result.get("web_items", []),
        "errors": result.get("errors", []),
    }


def fetch_social_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Search social media (X/Twitter & Reddit) using Tavily."""
    if state.get("skip_social", False):
        print("⏭️  Skipping social media (skip_social=True)")
        return {"social_items": []}

    from .nodes.social_search import search_social_media
    from .models import AgentState

    agent_state = AgentState(
        keywords=state.get("keywords", []),
        errors=state.get("errors", []),
    )
    result = search_social_media(agent_state)
    return {
        "social_items": result.get("social_items", []),
        "errors": result.get("errors", []),
    }


def fetch_newsapi_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Fetch news from NewsAPI."""
    if state.get("skip_newsapi", False):
        print("⏭️  Skipping NewsAPI (skip_newsapi=True)")
        return {"newsapi_items": []}

    from .nodes.newsapi_fetcher import fetch_newsapi
    from .models import AgentState

    agent_state = AgentState(
        keywords=state.get("keywords", []),
        errors=state.get("errors", []),
    )
    result = fetch_newsapi(agent_state)
    return {
        "newsapi_items": result.get("newsapi_items", []),
        "errors": result.get("errors", []),
    }


def deduplicate_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Remove duplicate items and filter out previously processed URLs."""
    from .nodes.deduplicator import deduplicate_all_sources
    from .models import AgentState

    # Check if we should use Feishu Base for history
    use_feishu_history = state.get("use_feishu_history", False)
    skip_local_output = state.get("skip_local_output", False)

    agent_state = AgentState(
        keywords=state.get("keywords", []),
        rss_items=state.get("rss_items", []),
        web_items=state.get("web_items", []),
        social_items=state.get("social_items", []),
        newsapi_items=state.get("newsapi_items", []),
        errors=state.get("errors", []),
    )
    result = deduplicate_all_sources(
        agent_state,
        use_feishu_history=use_feishu_history,
        skip_save_history=skip_local_output,  # Don't save local history if skipping local output
    )
    return {
        "rss_items": result.get("rss_items", []),
        "web_items": result.get("web_items", []),
        "social_items": result.get("social_items", []),
        "newsapi_items": result.get("newsapi_items", []),
    }


def summarize_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Summarize and analyze sentiment using Gemini."""
    from .nodes.summarizer import summarize_and_analyze
    from .models import AgentState

    agent_state = AgentState(
        keywords=state.get("keywords", []),
        rss_items=state.get("rss_items", []),
        web_items=state.get("web_items", []),
        social_items=state.get("social_items", []),
        newsapi_items=state.get("newsapi_items", []),
        errors=state.get("errors", []),
    )
    result = summarize_and_analyze(agent_state)
    return {
        "processed_items": result.get("processed_items", []),
        "errors": result.get("errors", []),
    }


def pass_through_without_summary_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Pass items through as 'processed' without AI summarization.
    
    Used when skip_summarize=True for faster testing.
    """
    from .models import Sentiment

    all_items = (
        state.get("rss_items", [])
        + state.get("web_items", [])
        + state.get("social_items", [])
        + state.get("newsapi_items", [])
    )

    # Just mark items as processed with neutral sentiment and use content as summary
    for item in all_items:
        item.sentiment = Sentiment.NEUTRAL
        item.summary = item.content[:500] if item.content else "(no content)"

    return {"processed_items": all_items}


def generate_output_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Generate markdown output."""
    from .nodes.output_generator import generate_markdown_output
    from .models import AgentState

    agent_state = AgentState(
        keywords=state.get("keywords", []),
        processed_items=state.get("processed_items", []),
        errors=state.get("errors", []),
    )
    result = generate_markdown_output(agent_state)
    return {
        "markdown_output": result.get("markdown_output", ""),
    }


def save_report_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Save the markdown and HTML reports to files."""
    from .nodes.html_generator import convert_markdown_file_to_html
    
    # Check if we should skip local output
    skip_local_output = state.get("skip_local_output", False)
    markdown_output = state.get("markdown_output", "")

    if not markdown_output:
        return {"output_file": "", "html_file": ""}

    if skip_local_output:
        print("⏭️  Skipping local output (skip_local_output=True)")
        return {"output_file": "", "html_file": ""}

    settings = get_settings()

    # Create output directory
    output_path = Path(settings.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    md_filename = f"news_report_{timestamp}.md"
    md_filepath = output_path / md_filename

    # Save the markdown report
    with open(md_filepath, "w", encoding="utf-8") as f:
        f.write(markdown_output)

    # Also generate HTML version
    try:
        html_filepath = convert_markdown_file_to_html(md_filepath)
    except Exception:
        html_filepath = ""

    return {
        "output_file": str(md_filepath.absolute()),
        "html_file": html_filepath,
    }


def export_feishu_node(state: NewsAgentState) -> dict[str, Any]:
    """Node: Export news items to Feishu spreadsheet."""
    if state.get("skip_feishu", False):
        print("⏭️  Skipping Feishu export (skip_feishu=True)")
        return {"feishu_export": {"success": False, "message": "Skipped"}}

    from .nodes.feishu_exporter import export_to_feishu

    processed_items = state.get("processed_items", [])
    result = export_to_feishu(processed_items)
    
    return {"feishu_export": result}


def should_continue_to_summarize(state: NewsAgentState) -> str:
    """Determine if we have items to summarize."""
    # Skip summarization if requested
    if state.get("skip_summarize", False):
        print("⏭️  Skipping summarization (skip_summarize=True)")
        return "generate_output_no_summary"

    rss_items = state.get("rss_items", [])
    web_items = state.get("web_items", [])
    social_items = state.get("social_items", [])
    newsapi_items = state.get("newsapi_items", [])

    total_items = len(rss_items) + len(web_items) + len(social_items) + len(newsapi_items)

    if total_items > 0:
        return "summarize"
    else:
        return "generate_output"


def create_graph() -> StateGraph:
    """Create the news agent workflow graph.

    Workflow Structure:
    
        START
          │
          ▼
        fetch_rss (Parse RSS feeds)
          │
          ▼
        fetch_web (Scrape web pages via Firecrawl)
          │
          ▼
        fetch_social (X/Twitter & Reddit via Tavily)
          │
          ▼
        fetch_newsapi (NewsAPI)
          │
          ▼
        deduplicate (Remove duplicates & filter history)
          │
          ▼
        [conditional: items found?]
          │
          ├── yes ──► summarize (Gemini AI)
          │              │
          │              ▼
          └── no ───► generate_output (Markdown)
                         │
                         ▼
                      save_report (Save to file)
                         │
                         ▼
                      export_feishu (Export to Feishu table)
                         │
                         ▼
                        END
    """
    # Create the state graph with our state schema
    builder = StateGraph(NewsAgentState)

    # Add nodes for each step in the workflow
    builder.add_node("fetch_rss", fetch_rss_node)
    builder.add_node("fetch_web", fetch_web_node)
    builder.add_node("fetch_social", fetch_social_node)
    builder.add_node("fetch_newsapi", fetch_newsapi_node)
    builder.add_node("deduplicate", deduplicate_node)
    builder.add_node("summarize", summarize_node)
    builder.add_node("pass_through", pass_through_without_summary_node)
    builder.add_node("generate_output", generate_output_node)
    builder.add_node("save_report", save_report_node)
    builder.add_node("export_feishu", export_feishu_node)

    # Define the workflow edges
    builder.add_edge(START, "fetch_rss")
    builder.add_edge("fetch_rss", "fetch_web")
    builder.add_edge("fetch_web", "fetch_social")
    builder.add_edge("fetch_social", "fetch_newsapi")
    builder.add_edge("fetch_newsapi", "deduplicate")

    # Conditional edge: check if we have items to summarize (after deduplication)
    builder.add_conditional_edges(
        "deduplicate",
        should_continue_to_summarize,
        {
            "summarize": "summarize",
            "generate_output": "generate_output",
            "generate_output_no_summary": "pass_through",
        },
    )

    # summarize -> generate_output
    builder.add_edge("summarize", "generate_output")
    # pass_through (no summary) -> generate_output
    builder.add_edge("pass_through", "generate_output")

    # generate_output -> save_report -> export_feishu -> END
    builder.add_edge("generate_output", "save_report")
    builder.add_edge("save_report", "export_feishu")
    builder.add_edge("export_feishu", END)

    return builder


# Compile the graph for langgraph dev
# This is the entry point referenced in langgraph.json
graph = create_graph().compile()


# Alternative: Function to create graph with custom configuration
def make_graph(config: dict | None = None):
    """Create a configured graph instance.
    
    This can be used for dynamic graph configuration via langgraph.json.
    """
    return create_graph().compile()
