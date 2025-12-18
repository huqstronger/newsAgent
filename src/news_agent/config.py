"""Configuration management for News Agent."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RSSFeed(BaseModel):
    """RSS feed configuration."""

    name: str
    url: str
    category: str = "general"
    limit: int = 10  # Max number of entries to fetch


class WebPage(BaseModel):
    """Web page configuration."""

    name: str
    url: str
    selector: str = "article"
    category: str = "general"
    limit: int = 5  # Max number of articles to extract
    wait_for: int = 0  # Milliseconds to wait for JS to load (0 = no wait)


class SocialMediaConfig(BaseModel):
    """Social media search configuration."""

    platforms: list[str] = Field(default_factory=lambda: ["x.com", "reddit.com"])


class OutputConfig(BaseModel):
    """Output configuration."""

    format: str = "markdown"
    include_source_links: bool = True
    max_items_per_source: int = 10
    summary_max_words: int = 150


class SourcesConfig(BaseModel):
    """Complete sources configuration."""

    keywords: list[str] = Field(default_factory=list)
    rss_feeds: list[RSSFeed] = Field(default_factory=list)
    web_pages: list[WebPage] = Field(default_factory=list)
    social_media: SocialMediaConfig = Field(default_factory=SocialMediaConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    firecrawl_api_key: str = Field(default="", alias="FIRECRAWL_API_KEY")
    newsapi_api_key: str = Field(default="", alias="NEWSAPI_API_KEY")
    output_dir: str = Field(default="./output", alias="OUTPUT_DIR")
    config_path: str = Field(default="./config/sources.yaml", alias="CONFIG_PATH")


def load_sources_config(config_path: str | Path) -> SourcesConfig:
    """Load sources configuration from YAML file."""
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    return SourcesConfig(**data)


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()


def get_sources_config(settings: Settings | None = None) -> SourcesConfig:
    """Get sources configuration."""
    if settings is None:
        settings = get_settings()
    return load_sources_config(settings.config_path)

