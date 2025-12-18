"""LangGraph workflow for news agent.

This module provides convenience functions for running the news agent.
The graph definition is in graph.py for langgraph dev compatibility.
"""

from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from .graph import (
    NewsAgentState,
    create_graph,
    graph,
    save_report_node,
)
from .config import get_sources_config, get_settings


# Re-export for backward compatibility
__all__ = [
    "NewsAgentState",
    "create_graph",
    "graph",
    "compile_workflow",
    "run_news_agent",
    "stream_news_agent",
    "get_workflow_visualization",
]


def compile_workflow(checkpointer: MemorySaver | None = None):
    """Compile the workflow into an executable graph.

    Args:
        checkpointer: Optional memory saver for persistence.

    Returns:
        Compiled graph ready for execution.
    """
    builder = create_graph()

    if checkpointer:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


def run_news_agent(
    keywords: list[str] | None = None,
    thread_id: str | None = None,
    feishu_only: bool = False,
) -> dict[str, Any]:
    """Run the news agent workflow.

    Args:
        keywords: Optional list of keywords to filter content.
                  If not provided, uses keywords from config.
        thread_id: Optional thread ID for persistence.
        feishu_only: If True, skip local output and use Feishu Base for dedup/export.

    Returns:
        The final state containing markdown output and any errors.
    """
    settings = get_settings()
    sources_config = get_sources_config(settings)

    # Use provided keywords or fall back to config
    effective_keywords = keywords if keywords else sources_config.keywords

    # Create checkpointer for persistence if thread_id provided
    checkpointer = None
    config = {}

    if thread_id:
        checkpointer = MemorySaver()
        config = {"configurable": {"thread_id": thread_id}}

    # Compile the workflow
    compiled_graph = compile_workflow(checkpointer=checkpointer)

    # Create initial state
    initial_state: NewsAgentState = {
        "keywords": effective_keywords,
        "skip_rss": False,
        "skip_web": False,
        "skip_social": False,
        "skip_newsapi": False,
        "skip_summarize": False,
        "skip_feishu": not feishu_only,  # Don't skip Feishu if feishu_only mode
        "skip_local_output": feishu_only,
        "use_feishu_history": feishu_only,
        "rss_items": [],
        "web_items": [],
        "social_items": [],
        "newsapi_items": [],
        "processed_items": [],
        "markdown_output": "",
        "output_file": "",
        "html_file": "",
        "feishu_export": {},
        "errors": [],
        "messages": [],
    }

    # Run the workflow
    if config:
        final_state = compiled_graph.invoke(initial_state, config=config)
    else:
        final_state = compiled_graph.invoke(initial_state)

    return final_state


def stream_news_agent(
    keywords: list[str] | None = None,
    thread_id: str | None = None,
    feishu_only: bool = False,
):
    """Stream the news agent workflow execution.

    Args:
        keywords: Optional list of keywords to filter content.
        thread_id: Optional thread ID for persistence.
        feishu_only: If True, skip local output and use Feishu Base for dedup/export.

    Yields:
        Updates from each node as they complete.
    """
    settings = get_settings()
    sources_config = get_sources_config(settings)

    effective_keywords = keywords if keywords else sources_config.keywords

    checkpointer = None
    config = {}

    if thread_id:
        checkpointer = MemorySaver()
        config = {"configurable": {"thread_id": thread_id}}

    compiled_graph = compile_workflow(checkpointer=checkpointer)

    initial_state: NewsAgentState = {
        "keywords": effective_keywords,
        "skip_rss": False,
        "skip_web": False,
        "skip_social": False,
        "skip_newsapi": False,
        "skip_summarize": False,
        "skip_feishu": not feishu_only,  # Don't skip Feishu if feishu_only mode
        "skip_local_output": feishu_only,
        "use_feishu_history": feishu_only,
        "rss_items": [],
        "web_items": [],
        "social_items": [],
        "newsapi_items": [],
        "processed_items": [],
        "markdown_output": "",
        "output_file": "",
        "html_file": "",
        "feishu_export": {},
        "errors": [],
        "messages": [],
    }

    # Stream updates
    if config:
        for chunk in compiled_graph.stream(initial_state, config=config, stream_mode="updates"):
            yield chunk
    else:
        for chunk in compiled_graph.stream(initial_state, stream_mode="updates"):
            yield chunk


def get_workflow_visualization() -> str:
    """Get a Mermaid diagram of the workflow."""
    try:
        return graph.get_graph().draw_mermaid()
    except Exception:
        return "Visualization not available"
