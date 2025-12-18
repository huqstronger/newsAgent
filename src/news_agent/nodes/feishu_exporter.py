"""Feishu Base (Bitable) exporter node.

Exports news items to a Feishu Base (多维表格).

Requires environment variables:
- FEISHU_APP_ID: App ID from Feishu Open Platform
- FEISHU_APP_SECRET: App Secret from Feishu Open Platform
- FEISHU_BASE_APP_TOKEN: The Base app token (from URL, e.g., AOcUwIdxEiJiEXkWwAkczxmxnWe)
- FEISHU_BASE_TABLE_ID: The table ID (from URL, e.g., tbliXK5rNy9NH3Yo)
"""

import os
from datetime import datetime
from typing import Any

import requests

from ..models import NewsItem, Sentiment


def get_tenant_access_token() -> str | None:
    """Get Feishu tenant access token.
    
    Uses app_id and app_secret to get access token.
    """
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    
    if not app_id or not app_secret:
        print("⚠️  Feishu credentials not configured (FEISHU_APP_ID, FEISHU_APP_SECRET)")
        return None
    
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
    post_data = {"app_id": app_id, "app_secret": app_secret}
    
    try:
        response = requests.post(url, json=post_data)
        result = response.json()
        
        if result.get("code") == 0:
            return result.get("tenant_access_token")
        else:
            print(f"⚠️  Feishu auth error: {result.get('msg')}")
            return None
    except Exception as e:
        print(f"⚠️  Feishu auth request failed: {e}")
        return None


def get_table_fields(token: str, app_token: str, table_id: str) -> list[dict] | None:
    """Get the field definitions for a table.
    
    This helps us understand what columns exist in the table.
    """
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        result = response.json()
        
        if result.get("code") == 0:
            fields = result.get("data", {}).get("items", [])
            return fields
        else:
            print(f"⚠️  Failed to get table fields: {result.get('msg')}")
            return None
    except Exception as e:
        print(f"⚠️  Failed to query table fields: {e}")
        return None


def create_default_fields(token: str, app_token: str, table_id: str) -> bool:
    """Create default fields if they don't exist.
    
    Expected fields: Title, Source, Category, Sentiment, Keywords, Summary, URL, Date
    """
    existing_fields = get_table_fields(token, app_token, table_id)
    if existing_fields is None:
        return False
    
    existing_names = {f.get("field_name") for f in existing_fields}
    
    required_fields = [
        {"field_name": "Title", "type": 1},      # Text
        {"field_name": "Source", "type": 1},     # Text
        {"field_name": "Category", "type": 1},   # Text
        {"field_name": "Sentiment", "type": 1},  # Text
        {"field_name": "Keywords", "type": 1},   # Text
        {"field_name": "Summary", "type": 1},    # Text
        {"field_name": "URL", "type": 15},       # URL
        {"field_name": "Date", "type": 5},       # DateTime
    ]
    
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    for field in required_fields:
        if field["field_name"] not in existing_names:
            try:
                response = requests.post(url, json=field, headers=headers)
                result = response.json()
                if result.get("code") == 0:
                    print(f"   Created field: {field['field_name']}")
                else:
                    print(f"   ⚠️  Could not create field {field['field_name']}: {result.get('msg')}")
            except Exception as e:
                print(f"   ⚠️  Error creating field {field['field_name']}: {e}")
    
    return True


def sentiment_to_text(sentiment: Sentiment) -> str:
    """Convert sentiment to text with emoji."""
    if sentiment == Sentiment.POSITIVE:
        return "🟢 Positive"
    elif sentiment == Sentiment.NEGATIVE:
        return "🔴 Negative"
    else:
        return "🟡 Neutral"


def format_category(category: str) -> str:
    """Format category name for display (e.g., 'company_blog' -> 'Company Blog')."""
    if not category:
        return "General"
    # Replace underscores with spaces and title case
    return category.replace("_", " ").title()


def batch_create_records(token: str, app_token: str, table_id: str, records: list[dict]) -> dict[str, Any]:
    """Batch create records in Feishu Base.
    
    Args:
        token: Tenant access token
        app_token: Base app token
        table_id: Table ID
        records: List of record objects with 'fields' key
        
    Returns:
        API response
    """
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Bitable batch create accepts max 500 records at a time
    batch_size = 500
    total_created = 0
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        data = {"records": batch}
        
        try:
            response = requests.post(url, json=data, headers=headers)
            result = response.json()
            
            if result.get("code") == 0:
                created = len(result.get("data", {}).get("records", []))
                total_created += created
            else:
                print(f"⚠️  Batch create error: {result.get('msg')}")
                return {
                    "success": False,
                    "message": result.get("msg"),
                    "items_created": total_created,
                }
        except Exception as e:
            print(f"⚠️  Batch create request failed: {e}")
            return {
                "success": False,
                "message": str(e),
                "items_created": total_created,
            }
    
    return {
        "success": True,
        "message": f"Created {total_created} records",
        "items_created": total_created,
    }


def fetch_existing_urls_from_feishu() -> set[str]:
    """Fetch all existing URLs from Feishu Base for deduplication.
    
    Returns:
        Set of URLs that have already been exported to Feishu Base.
    """
    app_token = os.environ.get("FEISHU_BASE_APP_TOKEN", "")
    table_id = os.environ.get("FEISHU_BASE_TABLE_ID", "")
    
    if not app_token or not table_id:
        print("⚠️  Feishu Base not configured, cannot fetch existing URLs")
        return set()
    
    token = get_tenant_access_token()
    if not token:
        print("⚠️  Failed to get Feishu access token")
        return set()
    
    urls: set[str] = set()
    page_token: str | None = None
    
    # Paginate through all records to get URLs
    while True:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        headers = {"Authorization": f"Bearer {token}"}
        params: dict[str, Any] = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        
        try:
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            if result.get("code") != 0:
                print(f"⚠️  Failed to fetch records: {result.get('msg')}")
                break
            
            records = result.get("data", {}).get("items", [])
            for record in records:
                fields = record.get("fields", {})
                url_field = fields.get("URL", {})
                if isinstance(url_field, dict):
                    link = url_field.get("link", "")
                    if link:
                        urls.add(link)
                elif isinstance(url_field, str):
                    urls.add(url_field)
            
            # Check for more pages
            has_more = result.get("data", {}).get("has_more", False)
            page_token = result.get("data", {}).get("page_token")
            
            if not has_more:
                break
                
        except Exception as e:
            print(f"⚠️  Error fetching records: {e}")
            break
    
    print(f"📋 Fetched {len(urls)} existing URLs from Feishu Base")
    return urls


def export_to_feishu(processed_items: list[NewsItem]) -> dict[str, Any]:
    """Export news items to Feishu Base (Bitable).
    
    Creates records with columns:
    - Title
    - Source
    - Category
    - Sentiment
    - Keywords
    - Summary
    - URL
    - Date
    
    Returns:
        Dict with success status and message
    """
    # Get config from environment
    app_token = os.environ.get("FEISHU_BASE_APP_TOKEN", "")
    table_id = os.environ.get("FEISHU_BASE_TABLE_ID", "")
    
    if not app_token or not table_id:
        return {
            "success": False,
            "message": "Feishu Base not configured (FEISHU_BASE_APP_TOKEN, FEISHU_BASE_TABLE_ID)",
        }
    
    if not processed_items:
        return {
            "success": True,
            "message": "No items to export",
            "items_exported": 0,
        }
    
    # Get access token
    token = get_tenant_access_token()
    if not token:
        return {
            "success": False,
            "message": "Failed to get Feishu access token",
        }
    
    print(f"📊 Exporting {len(processed_items)} items to Feishu Base...")
    
    # Prepare records
    records = []
    for item in processed_items:
        # Date needs to be in milliseconds timestamp for Bitable
        date_timestamp = None
        if item.published_at:
            date_timestamp = int(item.published_at.timestamp() * 1000)
        else:
            date_timestamp = int(datetime.now().timestamp() * 1000)
        
        record = {
            "fields": {
                "Title": item.title,
                "Source": item.source_name,
                "Category": format_category(item.category),
                "Sentiment": sentiment_to_text(item.sentiment),
                "Keywords": ", ".join(item.keywords_matched),
                "Summary": item.summary[:2000] if item.summary else "",
                "URL": {
                    "link": item.url,
                    "text": item.title,
                },
                "Date": date_timestamp,
            }
        }
        records.append(record)
    
    # Create records
    result = batch_create_records(token, app_token, table_id, records)
    
    if result["success"]:
        print(f"✅ Exported {result['items_created']} items to Feishu Base")
        return {
            "success": True,
            "message": f"Exported {result['items_created']} items to Feishu Base",
            "items_exported": result["items_created"],
        }
    else:
        return {
            "success": False,
            "message": f"Failed to export: {result['message']}",
        }
