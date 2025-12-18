#!/bin/bash
# Daily News Agent Runner
# Add to crontab: 0 21 * * * /home/qhu/Workspace/newsAgent/scripts/run_daily.sh
#
# Options:
#   --feishu-only : Skip local output, use Feishu Base for deduplication and export
#                   (no files saved to output/ folder, history managed by Feishu)

set -e

# Change to project directory
cd /home/qhu/Workspace/newsAgent

# Create logs directory if it doesn't exist
mkdir -p logs

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Run the news agent
# Uncomment the --feishu-only flag below to use Feishu Base as the only storage
echo "$(date): Starting News Agent..."
uv run python -m news_agent.main --once --feishu-only >> logs/news_agent.log 2>&1
# uv run python -m news_agent.main --once >> logs/news_agent.log 2>&1  # Use this for local output

echo "$(date): News Agent completed."

