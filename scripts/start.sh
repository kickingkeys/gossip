#!/usr/bin/env bash
# Donny — Launch Script
# Starts the Python portal, optional tunnel, and OpenClaw gateway

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

export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

PORT="${PORTAL_PORT:-3000}"

echo ""
echo "  Starting Donny..."
echo ""

# Initialize database
python -c "from gossip.db import init_db; init_db()"

# Trim old donny_memory entries
python -c "from gossip.db import trim_donny_memory; trimmed = trim_donny_memory(); print(f'  Trimmed {trimmed} old memory entries') if trimmed else None"

# Create data directories
mkdir -p "$PROJECT_ROOT/data/logs"
mkdir -p "$PROJECT_ROOT/data/summaries"
mkdir -p "$PROJECT_ROOT/data/dossiers"
mkdir -p "$PROJECT_ROOT/data/chat"

# Start Python portal in background
echo "  Starting portal on port $PORT..."
cd "$PROJECT_ROOT" && python -m portal.app &
PORTAL_PID=$!
sleep 2

# Start public tunnel (optional)
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
        # Write tunnel URL to .env so OAuth callback can read it
        if grep -q "^PORTAL_PUBLIC_URL=" "$PROJECT_ROOT/config/.env" 2>/dev/null; then
            sed -i '' "s|^PORTAL_PUBLIC_URL=.*|PORTAL_PUBLIC_URL=$PUBLIC_URL|" "$PROJECT_ROOT/config/.env"
        else
            echo "PORTAL_PUBLIC_URL=$PUBLIC_URL" >> "$PROJECT_ROOT/config/.env"
        fi
    fi

    if [ -z "$PUBLIC_URL" ]; then
        echo "  Warning: Cloudflare tunnel started but URL not detected yet"
        echo "  Check /tmp/cloudflared.log for the URL"
    fi
else
    echo "  No tunnel available (install cloudflared: brew install cloudflared)"
    echo "  Portal accessible locally only: http://localhost:$PORT"
fi

# Start OpenClaw gateway (if installed)
OPENCLAW_PID=""
if command -v openclaw &>/dev/null; then
    echo "  Starting OpenClaw gateway..."
    cd "$PROJECT_ROOT/openclaw"
    export GOSSIP_API_URL="http://localhost:$PORT/api/gossip"
    openclaw --profile gossip gateway &
    OPENCLAW_PID=$!
else
    echo "  OpenClaw not installed — bot will not connect to Discord"
    echo "  Install OpenClaw: https://github.com/openclaw/openclaw"
    echo "  Portal API is running at http://localhost:$PORT/api/gossip/"
fi

# Get invite token
INVITE_TOKEN=$(python -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT')
from gossip.config import load_config; load_config()
from gossip.db import get_default_group
g = get_default_group()
print(g['invite_token'] if g else 'NO_GROUP')
")

echo ""
echo "  Portal PID: $PORTAL_PID"
if [ -n "$OPENCLAW_PID" ]; then echo "  OpenClaw PID: $OPENCLAW_PID"; fi
if [ -n "$TUNNEL_PID" ]; then echo "  Tunnel PID: $TUNNEL_PID"; fi
echo ""
echo "  Donny is running!"
echo "  Local: http://localhost:$PORT"
if [ -n "$PUBLIC_URL" ]; then
    echo ""
    echo "  Public URL: $PUBLIC_URL"
    echo ""
    echo "  Onboarding: $PUBLIC_URL/join/$INVITE_TOKEN"
    echo "  Map:         $PUBLIC_URL/map/$INVITE_TOKEN"
fi
echo ""
echo "  API: http://localhost:$PORT/api/gossip/"
echo ""
echo "  Press Ctrl+C to stop"

# Trap Ctrl+C to kill all processes
trap "kill $PORTAL_PID $OPENCLAW_PID $TUNNEL_PID 2>/dev/null; echo '  Stopped.'; exit 0" INT TERM

# Wait for any process to exit
wait
