"""Main entry point for News Agent."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import schedule
import time

# Load environment variables from .env file
load_dotenv()

from .config import get_settings, get_sources_config
from .workflow import run_news_agent, stream_news_agent, get_workflow_visualization


def save_report(markdown_content: str, output_dir: str) -> Path:
    """Save the markdown report to a file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"news_report_{timestamp}.md"
    filepath = output_path / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return filepath


def run_with_streaming(keywords: list[str] | None = None, feishu_only: bool = False):
    """Run the news agent with streaming output to show progress.
    
    Args:
        keywords: Optional list of keywords to filter content.
        feishu_only: If True, skip local output and use Feishu Base for dedup/export.
    """
    settings = get_settings()

    print(f"\n{'='*60}")
    print(f"Running News Agent - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if feishu_only:
        print("Mode: Feishu-only (no local output)")
    print(f"{'='*60}\n")

    final_state = {}

    try:
        print("📊 Workflow Progress:")
        print("-" * 40)

        for update in stream_news_agent(keywords=keywords, feishu_only=feishu_only):
            for node_name, node_output in update.items():
                if node_name == "fetch_rss":
                    items = node_output.get("rss_items", [])
                    print(f"  • RSS Feeds: ✅ Complete ({len(items)} items)")

                elif node_name == "fetch_web":
                    items = node_output.get("web_items", [])
                    print(f"  • Web Pages: ✅ Complete ({len(items)} items)")

                elif node_name == "fetch_social":
                    items = node_output.get("social_items", [])
                    print(f"  • Social Media: ✅ Complete ({len(items)} items)")

                elif node_name == "fetch_newsapi":
                    items = node_output.get("newsapi_items", [])
                    print(f"  • NewsAPI: ✅ Complete ({len(items)} items)")

                elif node_name == "deduplicate":
                    # Count total after dedup
                    rss = len(node_output.get("rss_items", []))
                    web = len(node_output.get("web_items", []))
                    social = len(node_output.get("social_items", []))
                    newsapi = len(node_output.get("newsapi_items", []))
                    total = rss + web + social + newsapi
                    print(f"  • Deduplication: ✅ Complete ({total} unique items)")

                elif node_name == "summarize":
                    items = node_output.get("processed_items", [])
                    print(f"  • Summarization: ✅ Complete ({len(items)} summaries)")

                elif node_name == "pass_through":
                    items = node_output.get("processed_items", [])
                    print(f"  • Pass-through: ✅ Complete ({len(items)} items)")

                elif node_name == "generate_output":
                    output = node_output.get("markdown_output", "")
                    lines = len(output.split("\n")) if output else 0
                    print(f"  • Report Generation: ✅ Complete ({lines} lines)")

                elif node_name == "save_report":
                    output_file = node_output.get("output_file", "")
                    html_file = node_output.get("html_file", "")
                    print(f"  • Save Report: ✅ Complete")

                elif node_name == "export_feishu":
                    feishu_result = node_output.get("feishu_export", {})
                    if feishu_result.get("success"):
                        count = feishu_result.get("items_exported", 0)
                        print(f"  • Feishu Export: ✅ Complete ({count} items)")
                    else:
                        msg = feishu_result.get("message", "Unknown error")
                        print(f"  • Feishu Export: ⚠️ {msg}")

                # Merge into final state
                final_state.update(node_output)

        print("-" * 40)

    except Exception as e:
        print(f"❌ Error during workflow: {e}")
        raise

    return final_state


def run_daily_job(keywords: list[str] | None = None, use_streaming: bool = True, feishu_only: bool = False):
    """Run the news agent job.
    
    Args:
        keywords: Optional list of keywords to filter content.
        use_streaming: If True, show streaming progress updates.
        feishu_only: If True, skip local output and use Feishu Base for dedup/export.
    """
    settings = get_settings()

    try:
        if use_streaming:
            result = run_with_streaming(keywords=keywords, feishu_only=feishu_only)
        else:
            print(f"\n{'='*60}")
            print(f"Running News Agent - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}\n")
            result = run_news_agent(keywords=keywords, feishu_only=feishu_only)

        # Report is already saved by save_report_node in the workflow
        output_file = result.get("output_file", "") if result else ""
        html_file = result.get("html_file", "") if result else ""
        
        if output_file:
            print(f"\n✅ Report saved to: {output_file}")
            if html_file:
                print(f"   HTML version: {html_file}")
        elif not feishu_only:
            print("\n⚠️ No output generated")
        # In feishu_only mode, no local output is expected

        # Print Feishu export status
        feishu_result = result.get("feishu_export", {}) if result else {}
        if feishu_result.get("success"):
            print(f"✅ Feishu export: {feishu_result.get('items_exported', 0)} items uploaded")
        elif feishu_result.get("message") and feishu_result.get("message") != "Skipped":
            print(f"⚠️ Feishu export: {feishu_result.get('message')}")

        # Print any errors
        errors = result.get("errors", []) if result else []
        if errors:
            print(f"\n⚠️ {len(errors)} warning(s) during processing:")
            for error in errors[:10]:  # Limit error output
                print(f"  - {error}")

        # Print statistics
        processed = result.get("processed_items", []) if result else []
        print(f"\n📊 Statistics:")
        print(f"  - Total items processed: {len(processed)}")

        if processed:
            from .models import Sentiment

            positive = sum(1 for i in processed if i.sentiment == Sentiment.POSITIVE)
            negative = sum(1 for i in processed if i.sentiment == Sentiment.NEGATIVE)
            neutral = sum(1 for i in processed if i.sentiment == Sentiment.NEUTRAL)
            print(f"  - Positive: 🟢 {positive}")
            print(f"  - Negative: 🔴 {negative}")
            print(f"  - Neutral:  🟡 {neutral}")

    except Exception as e:
        print(f"❌ Error running news agent: {e}")
        raise


def show_workflow():
    """Display the workflow visualization."""
    print("\n📈 News Agent Workflow Diagram (Mermaid):\n")
    print(get_workflow_visualization())
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="News Agent - Aggregate and analyze news using AI (LangGraph)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (don't schedule)",
    )
    parser.add_argument(
        "--schedule",
        type=str,
        default="08:00",
        help="Time to run daily (HH:MM format, default: 08:00)",
    )
    parser.add_argument(
        "--keywords",
        type=str,
        nargs="+",
        help="Keywords to filter content (overrides config)",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory for reports",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming output (run in batch mode)",
    )
    parser.add_argument(
        "--show-workflow",
        action="store_true",
        help="Show the workflow diagram and exit",
    )
    parser.add_argument(
        "--feishu-only",
        action="store_true",
        help="Skip local output, use Feishu Base as the only storage (dedup from Feishu, export to Feishu)",
    )

    args = parser.parse_args()

    # Show workflow diagram if requested
    if args.show_workflow:
        show_workflow()
        return

    # Override settings if provided
    if args.config:
        import os

        os.environ["CONFIG_PATH"] = args.config
    if args.output:
        import os

        os.environ["OUTPUT_DIR"] = args.output

    # Validate configuration
    try:
        settings = get_settings()
        sources_config = get_sources_config(settings)
        print(f"📋 Loaded {len(sources_config.rss_feeds)} RSS feeds")
        print(f"📋 Loaded {len(sources_config.web_pages)} web pages")
        print(f"📋 Keywords: {', '.join(sources_config.keywords[:5])}...")
    except FileNotFoundError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)

    keywords = args.keywords
    use_streaming = not args.no_stream
    feishu_only = args.feishu_only

    if feishu_only:
        print("🌐 Feishu-only mode: Local output disabled, using Feishu Base for history")

    if args.once:
        # Run once and exit
        run_daily_job(keywords=keywords, use_streaming=use_streaming, feishu_only=feishu_only)
    else:
        # Schedule daily execution
        schedule_time = args.schedule
        print(f"\n⏰ Scheduling daily run at {schedule_time}")
        print("Press Ctrl+C to stop\n")

        # Run immediately on start
        run_daily_job(keywords=keywords, use_streaming=use_streaming, feishu_only=feishu_only)

        # Schedule for daily runs
        schedule.every().day.at(schedule_time).do(
            run_daily_job, keywords=keywords, use_streaming=use_streaming, feishu_only=feishu_only
        )

        # Keep running
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            print("\n\n👋 Shutting down...")
            sys.exit(0)


if __name__ == "__main__":
    main()
