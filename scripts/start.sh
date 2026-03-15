#!/usr/bin/env bash
# Gossip Bot — Launch Script
# Starts the Hermes gateway (bot), onboarding portal, and ngrok tunnel

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

NGROK_DOMAIN="superocular-floria-unriotously.ngrok-free.dev"
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

# Start ngrok tunnel in background
NGROK_PID=""
if command -v ngrok &>/dev/null; then
    echo "  Starting ngrok tunnel..."
    ngrok http --url="$NGROK_DOMAIN" "$PORT" --log=stdout --log-level=warn &>/dev/null &
    NGROK_PID=$!
    echo "  ngrok PID: $NGROK_PID"
else
    echo "  ngrok not installed — skipping tunnel (local access only)"
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

# Start Hermes gateway
from gateway.run import start_gateway
import asyncio
asyncio.run(start_gateway())
" &
HERMES_PID=$!

echo "  Portal PID: $PORTAL_PID"
echo "  Hermes PID: $HERMES_PID"
echo ""
echo "  Gossip bot is running!"
echo "  Local:  http://localhost:$PORT"
echo "  Public: https://$NGROK_DOMAIN"
echo ""
echo "  Onboarding: https://$NGROK_DOMAIN/join/$(python -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT')
from gossip.config import load_config; load_config()
from gossip.db import get_default_group
g = get_default_group()
print(g['invite_token'] if g else 'NO_GROUP')
")"
echo "  Map:         https://$NGROK_DOMAIN/map/$(python -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT')
from gossip.config import load_config; load_config()
from gossip.db import get_default_group
g = get_default_group()
print(g['invite_token'] if g else 'NO_GROUP')
")"
echo ""
echo "  Press Ctrl+C to stop"

# Trap Ctrl+C to kill all processes
trap "kill $PORTAL_PID $HERMES_PID $NGROK_PID 2>/dev/null; echo '  Stopped.'; exit 0" INT TERM

# Wait for either process to exit
wait
