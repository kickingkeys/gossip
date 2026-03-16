#!/usr/bin/env bash
# Gossip Bot — Launch Script
# Starts the Hermes gateway (bot), onboarding portal, and public tunnel

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Load environment
if [ -f "$PROJECT_ROOT/config/.env" ]; then
    set -a
    source "$PROJECT_ROOT/config/.env"
    set +a
fi

# Set Hermes home directory
export HERMES_HOME="$PROJECT_ROOT/config"
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/vendor/hermes-agent:$PYTHONPATH"

PORT="${PORTAL_PORT:-3000}"

echo ""
echo "  Starting Gossip Bot..."
echo ""

# Initialize database if needed
python -c "from gossip.db import init_db; init_db()"

# Install Hermes hooks (symlink from repo into $HERMES_HOME/hooks/)
HERMES_HOOKS_DIR="$HERMES_HOME/hooks"
mkdir -p "$HERMES_HOOKS_DIR"
if [ -d "$PROJECT_ROOT/hooks/gossip-logger" ] && [ ! -e "$HERMES_HOOKS_DIR/gossip-logger" ]; then
    ln -s "$PROJECT_ROOT/hooks/gossip-logger" "$HERMES_HOOKS_DIR/gossip-logger"
    echo "  Installed gossip-logger hook"
fi

# Initialize logging
python -c "from gossip.logger import setup_logging; setup_logging()"
mkdir -p "$PROJECT_ROOT/data/logs"

# Start portal in background
echo "  Starting onboarding portal on port $PORT..."
python -m portal.app &
PORTAL_PID=$!
sleep 2

# Start public tunnel
TUNNEL_PID=""
PUBLIC_URL=""

if command -v cloudflared &>/dev/null; then
    echo "  Starting Cloudflare tunnel..."
    cloudflared tunnel --url "http://localhost:$PORT" 2>/tmp/cloudflared.log &
    TUNNEL_PID=$!

    # Wait for the URL to appear in logs (up to 15 seconds)
    for i in $(seq 1 15); do
        PUBLIC_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -1)
        if [ -n "$PUBLIC_URL" ]; then break; fi
        sleep 1
    done

    if [ -n "$PUBLIC_URL" ]; then
        export PORTAL_PUBLIC_URL="$PUBLIC_URL"
    fi

    if [ -z "$PUBLIC_URL" ]; then
        echo "  Warning: Cloudflare tunnel started but URL not detected yet"
        echo "  Check /tmp/cloudflared.log for the URL"
    fi
else
    echo "  No tunnel available (install cloudflared: brew install cloudflared)"
    echo "  Portal accessible locally only: http://localhost:$PORT"
fi

# Start Hermes gateway
echo "  Starting Hermes gateway..."
echo ""

# Import gossip tools (registers them with Hermes registry), then start gateway
cd "$PROJECT_ROOT/vendor/hermes-agent"
python -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
sys.path.insert(0, '$PROJECT_ROOT/vendor/hermes-agent')

# Register gossip tools
import gossip_tools

# Patch Discord adapter with gossip-specific slash commands
from gossip.discord_commands import patch_discord_adapter
patch_discord_adapter()

# Start Hermes gateway
from gateway.run import start_gateway
import asyncio
asyncio.run(start_gateway())
" &
HERMES_PID=$!

# Get invite token
INVITE_TOKEN=$(python -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT')
from gossip.config import load_config; load_config()
from gossip.db import get_default_group
g = get_default_group()
print(g['invite_token'] if g else 'NO_GROUP')
")

echo "  Portal PID: $PORTAL_PID"
echo "  Hermes PID: $HERMES_PID"
if [ -n "$TUNNEL_PID" ]; then echo "  Tunnel PID: $TUNNEL_PID"; fi
echo ""
echo "  Gossip bot is running!"
echo "  Local: http://localhost:$PORT"
if [ -n "$PUBLIC_URL" ]; then
    echo ""
    echo "  Public URL: $PUBLIC_URL"
    echo ""
    echo "  Onboarding: $PUBLIC_URL/join/$INVITE_TOKEN"
    echo "  Map:         $PUBLIC_URL/map/$INVITE_TOKEN"
fi
echo ""
echo "  Press Ctrl+C to stop"

# Trap Ctrl+C to kill all processes
trap "kill $PORTAL_PID $HERMES_PID $TUNNEL_PID 2>/dev/null; echo '  Stopped.'; exit 0" INT TERM

# Wait for either process to exit
wait
