#!/usr/bin/env bash
# Gossip Bot — Launch Script
# Starts the Hermes gateway (bot) and the onboarding portal

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
echo "  Starting onboarding portal on port ${PORTAL_PORT:-3000}..."
python -m portal.app &
PORTAL_PID=$!

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
echo "  Portal: http://localhost:${PORTAL_PORT:-3000}"
echo ""
echo "  Press Ctrl+C to stop"

# Trap Ctrl+C to kill both processes
trap "kill $PORTAL_PID $HERMES_PID 2>/dev/null; echo '  Stopped.'; exit 0" INT TERM

# Wait for either process to exit
wait
