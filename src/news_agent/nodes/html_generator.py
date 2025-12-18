"""HTML report generator for news agent output."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import AgentState, NewsItem, Sentiment


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def markdown_to_html(md: str) -> str:
    """Convert basic markdown to HTML."""
    # Escape HTML first
    html = escape_html(md)
    
    # Headers
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    
    # Bold and italic
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    
    # Links (already escaped, need to unescape for href)
    html = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        lambda m: f'<a href="{m.group(2).replace("&amp;", "&")}" target="_blank" rel="noopener">{m.group(1)}</a>',
        html
    )
    
    # Code blocks
    html = re.sub(r'```(\w*)\n(.*?)```', r'<pre><code class="\1">\2</code></pre>', html, flags=re.DOTALL)
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
    
    # Paragraphs (double newlines)
    paragraphs = html.split('\n\n')
    processed = []
    for p in paragraphs:
        p = p.strip()
        if p and not p.startswith('<h') and not p.startswith('<pre') and not p.startswith('<ul') and not p.startswith('<li'):
            # Check if it's a list item
            if p.startswith('- '):
                items = p.split('\n')
                list_html = '<ul>'
                for item in items:
                    if item.startswith('- '):
                        list_html += f'<li>{item[2:]}</li>'
                list_html += '</ul>'
                processed.append(list_html)
            else:
                processed.append(f'<p>{p}</p>')
        else:
            processed.append(p)
    
    return '\n'.join(processed)


def get_sentiment_badge(sentiment: Sentiment) -> str:
    """Get HTML badge for sentiment."""
    badges = {
        Sentiment.POSITIVE: '<span class="badge positive">Positive</span>',
        Sentiment.NEGATIVE: '<span class="badge negative">Negative</span>',
        Sentiment.NEUTRAL: '<span class="badge neutral">Neutral</span>',
    }
    return badges.get(sentiment, badges[Sentiment.NEUTRAL])


def get_source_icon(source_type: str) -> str:
    """Get icon for source type."""
    icons = {
        "rss": "📰",
        "web_page": "🌐",
        "social_media": "💬",
        "newsapi": "📡",
    }
    return icons.get(source_type, "📄")


def format_news_item_html(item: NewsItem, index: int) -> str:
    """Format a single news item as HTML card."""
    sentiment_badge = get_sentiment_badge(item.sentiment)
    source_icon = get_source_icon(item.source_type)
    
    keywords_html = " ".join(
        f'<span class="keyword">{escape_html(kw)}</span>'
        for kw in item.keywords_matched[:5]
    )
    
    published = ""
    if item.published_at:
        published = f'<span class="date">{item.published_at.strftime("%b %d, %Y")}</span>'
    
    # Use summary if available, otherwise truncate content
    description = item.summary if item.summary else item.content[:300]
    if len(description) > 300:
        description = description[:297] + "..."
    
    return f'''
    <article class="news-card" data-sentiment="{item.sentiment.value if item.sentiment else 'neutral'}">
        <div class="card-header">
            <span class="source">{source_icon} {escape_html(item.source_name)}</span>
            {sentiment_badge}
            {published}
        </div>
        <h3 class="card-title">
            <a href="{escape_html(item.url)}" target="_blank" rel="noopener">{escape_html(item.title)}</a>
        </h3>
        <p class="card-description">{escape_html(description)}</p>
        <div class="card-keywords">{keywords_html}</div>
    </article>
    '''


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>News Report - {date}</title>
    <style>
        :root {{
            --bg-primary: #0f0f0f;
            --bg-secondary: #1a1a1a;
            --bg-card: #242424;
            --text-primary: #e8e8e8;
            --text-secondary: #a0a0a0;
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.3);
            --positive: #22c55e;
            --negative: #ef4444;
            --neutral: #eab308;
            --border: #333;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        header {{
            text-align: center;
            padding: 3rem 0;
            border-bottom: 1px solid var(--border);
            margin-bottom: 2rem;
            background: linear-gradient(180deg, var(--bg-secondary) 0%, var(--bg-primary) 100%);
        }}
        
        h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent) 0%, #a855f7 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.5rem;
        }}
        
        .subtitle {{
            color: var(--text-secondary);
            font-size: 1.1rem;
        }}
        
        .stats {{
            display: flex;
            justify-content: center;
            gap: 2rem;
            margin-top: 1.5rem;
            flex-wrap: wrap;
        }}
        
        .stat {{
            background: var(--bg-card);
            padding: 1rem 1.5rem;
            border-radius: 12px;
            border: 1px solid var(--border);
        }}
        
        .stat-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--accent);
        }}
        
        .stat-label {{
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}
        
        .filters {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
            justify-content: center;
        }}
        
        .filter-btn {{
            padding: 0.5rem 1rem;
            border: 1px solid var(--border);
            background: var(--bg-card);
            color: var(--text-primary);
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.9rem;
        }}
        
        .filter-btn:hover, .filter-btn.active {{
            background: var(--accent);
            border-color: var(--accent);
        }}
        
        .news-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.5rem;
        }}
        
        .news-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            transition: all 0.3s ease;
        }}
        
        .news-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
            border-color: var(--accent);
        }}
        
        .card-header {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}
        
        .source {{
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}
        
        .badge {{
            font-size: 0.75rem;
            padding: 0.25rem 0.6rem;
            border-radius: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .badge.positive {{
            background: rgba(34, 197, 94, 0.15);
            color: var(--positive);
            border: 1px solid rgba(34, 197, 94, 0.3);
        }}
        
        .badge.negative {{
            background: rgba(239, 68, 68, 0.15);
            color: var(--negative);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}
        
        .badge.neutral {{
            background: rgba(234, 179, 8, 0.15);
            color: var(--neutral);
            border: 1px solid rgba(234, 179, 8, 0.3);
        }}
        
        .date {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-left: auto;
        }}
        
        .card-title {{
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            line-height: 1.4;
        }}
        
        .card-title a {{
            color: var(--text-primary);
            text-decoration: none;
            transition: color 0.2s;
        }}
        
        .card-title a:hover {{
            color: var(--accent);
        }}
        
        .card-description {{
            color: var(--text-secondary);
            font-size: 0.95rem;
            margin-bottom: 1rem;
        }}
        
        .card-keywords {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        
        .keyword {{
            background: rgba(99, 102, 241, 0.15);
            color: var(--accent);
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        
        .errors {{
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 12px;
            padding: 1.5rem;
            margin-top: 2rem;
        }}
        
        .errors h3 {{
            color: var(--negative);
            margin-bottom: 1rem;
        }}
        
        .errors ul {{
            list-style: none;
        }}
        
        .errors li {{
            color: var(--text-secondary);
            padding: 0.25rem 0;
            font-size: 0.9rem;
        }}
        
        footer {{
            text-align: center;
            padding: 2rem;
            margin-top: 3rem;
            border-top: 1px solid var(--border);
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 1rem;
            }}
            
            h1 {{
                font-size: 1.75rem;
            }}
            
            .news-grid {{
                grid-template-columns: 1fr;
            }}
            
            .stats {{
                gap: 1rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📰 Daily News Report</h1>
            <p class="subtitle">AI-curated news from {date}</p>
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{total_items}</div>
                    <div class="stat-label">Articles</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{positive_count}</div>
                    <div class="stat-label">Positive</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{negative_count}</div>
                    <div class="stat-label">Negative</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{neutral_count}</div>
                    <div class="stat-label">Neutral</div>
                </div>
            </div>
        </header>
        
        <div class="filters">
            <button class="filter-btn active" onclick="filterCards('all')">All</button>
            <button class="filter-btn" onclick="filterCards('positive')">✓ Positive</button>
            <button class="filter-btn" onclick="filterCards('negative')">✗ Negative</button>
            <button class="filter-btn" onclick="filterCards('neutral')">○ Neutral</button>
        </div>
        
        <main class="news-grid">
            {news_items_html}
        </main>
        
        {errors_html}
        
        <footer>
            <p>Generated by News Agent • Powered by LangGraph + Gemini</p>
        </footer>
    </div>
    
    <script>
        function filterCards(sentiment) {{
            const cards = document.querySelectorAll('.news-card');
            const buttons = document.querySelectorAll('.filter-btn');
            
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            cards.forEach(card => {{
                if (sentiment === 'all' || card.dataset.sentiment === sentiment) {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}
    </script>
</body>
</html>
'''


def generate_html_output(state: AgentState) -> dict[str, Any]:
    """Generate an HTML report from processed news items."""
    items = state.processed_items
    errors = state.errors
    
    # Generate HTML for each news item
    news_items_html = "\n".join(
        format_news_item_html(item, i)
        for i, item in enumerate(items)
    )
    
    # Count sentiments
    positive_count = sum(1 for item in items if item.sentiment == Sentiment.POSITIVE)
    negative_count = sum(1 for item in items if item.sentiment == Sentiment.NEGATIVE)
    neutral_count = sum(1 for item in items if item.sentiment == Sentiment.NEUTRAL)
    
    # Errors section
    errors_html = ""
    if errors:
        error_items = "\n".join(f"<li>⚠️ {escape_html(err)}</li>" for err in errors)
        errors_html = f'''
        <div class="errors">
            <h3>Processing Notes</h3>
            <ul>{error_items}</ul>
        </div>
        '''
    
    # Generate final HTML
    html_output = HTML_TEMPLATE.format(
        date=datetime.now().strftime("%B %d, %Y"),
        total_items=len(items),
        positive_count=positive_count,
        negative_count=negative_count,
        neutral_count=neutral_count,
        news_items_html=news_items_html if news_items_html else "<p>No news items found matching your keywords.</p>",
        errors_html=errors_html,
    )
    
    return {
        "html_output": html_output,
    }


def convert_markdown_file_to_html(md_path: str | Path, html_path: str | Path | None = None) -> str:
    """Convert a markdown report file to HTML.
    
    Args:
        md_path: Path to the markdown file
        html_path: Optional path for HTML output. If not provided, uses same name with .html extension.
    
    Returns:
        Path to the generated HTML file
    """
    md_path = Path(md_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")
    
    # Read markdown content
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()
    
    # Convert markdown to HTML
    html_body = markdown_to_html(md_content)
    
    # Wrap in template
    date = datetime.now().strftime("%B %d, %Y")
    
    # Simple template for markdown conversion
    html_output = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>News Report - {date}</title>
    <style>
        :root {{
            --bg-primary: #0f0f0f;
            --bg-secondary: #1a1a1a;
            --text-primary: #e8e8e8;
            --text-secondary: #a0a0a0;
            --accent: #6366f1;
            --border: #333;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.7;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: var(--bg-secondary);
            padding: 3rem;
            border-radius: 16px;
            border: 1px solid var(--border);
        }}
        
        h1 {{
            font-size: 2rem;
            margin-bottom: 1.5rem;
            background: linear-gradient(135deg, var(--accent), #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        h2 {{
            font-size: 1.4rem;
            margin: 2rem 0 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
            color: var(--text-primary);
        }}
        
        h3 {{
            font-size: 1.1rem;
            margin: 1.5rem 0 0.75rem;
            color: var(--accent);
        }}
        
        p {{
            margin-bottom: 1rem;
            color: var(--text-secondary);
        }}
        
        a {{
            color: var(--accent);
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
        
        ul, ol {{
            margin: 1rem 0;
            padding-left: 1.5rem;
        }}
        
        li {{
            margin-bottom: 0.5rem;
            color: var(--text-secondary);
        }}
        
        code {{
            background: rgba(99, 102, 241, 0.1);
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-family: 'SF Mono', Consolas, monospace;
            font-size: 0.9em;
        }}
        
        pre {{
            background: var(--bg-primary);
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            margin: 1rem 0;
        }}
        
        pre code {{
            background: none;
            padding: 0;
        }}
        
        hr {{
            border: none;
            border-top: 1px solid var(--border);
            margin: 2rem 0;
        }}
        
        strong {{
            color: var(--text-primary);
        }}
    </style>
</head>
<body>
    <div class="container">
        {html_body}
    </div>
</body>
</html>
'''
    
    # Determine output path
    if html_path is None:
        html_path = md_path.with_suffix(".html")
    else:
        html_path = Path(html_path)
    
    # Write HTML file
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_output)
    
    return str(html_path)

