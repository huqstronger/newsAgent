# News Agent

A LangGraph-based news aggregation agent that extracts, summarizes, and analyzes news from multiple sources.

## Features

- **Multi-source**: RSS feeds, web pages (via Firecrawl), social media (X, Reddit via Tavily)
- **Keyword filtering**: Only extracts content matching configured keywords
- **AI summarization**: Uses Gemini for content summary and sentiment analysis
- **Markdown reports**: Organized output with source links and sentiment labels

## Quick Start

### 1. Install

```bash
uv pip install -e .
```

### 2. Configure

```bash
cp .env.template .env
# Edit .env with your API keys
```

Required API keys:
- `GOOGLE_API_KEY` - [Google AI Studio](https://aistudio.google.com/)
- `TAVILY_API_KEY` - [Tavily](https://tavily.com/)
- `FIRECRAWL_API_KEY` - [Firecrawl](https://firecrawl.dev/)

### 3. Run with LangGraph Dev

```bash
langgraph dev
```

Opens LangGraph Studio at `http://127.0.0.1:2024` for visual debugging.

## Configuration

Edit `config/sources.yaml`:

```yaml
keywords:
  - artificial intelligence
  - machine learning
  - LLM

rss_feeds:
  - name: TechCrunch AI
    url: https://techcrunch.com/category/artificial-intelligence/feed/
    category: tech_news

web_pages:
  - name: OpenAI Blog
    url: https://openai.com/blog
    selector: article

social_media:
  platforms:
    - x.com
    - reddit.com
```

## CLI Usage

```bash
# Run once
uv run python -m news_agent.main --once

# Custom keywords
uv run python -m news_agent.main --once --keywords "OpenAI" "GPT-5"

# Daily schedule
uv run python -m news_agent.main --schedule 08:00

# Show workflow diagram
uv run python -m news_agent.main --show-workflow
```

## Workflow

```
START → fetch_rss → fetch_web → fetch_social → summarize → generate_output → END
```

| Node | Description |
|------|-------------|
| `fetch_rss` | Parse RSS feeds |
| `fetch_web` | Scrape web pages (Firecrawl) |
| `fetch_social` | Tavily search (X, Reddit) |
| `summarize` | Gemini summarization + sentiment |
| `generate_output` | Markdown report |

## Project Structure

```
newsAgent/
├── langgraph.json         # LangGraph dev config
├── config/sources.yaml    # News sources
├── src/news_agent/
│   ├── graph.py           # LangGraph workflow
│   ├── config.py          # Settings
│   ├── models.py          # Data models
│   └── nodes/             # Workflow nodes
└── output/                # Generated reports
```

## License

MIT
