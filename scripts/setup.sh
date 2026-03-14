#!/usr/bin/env bash
# Gossip Bot — Interactive Setup Script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║         gossip bot setup               ║"
echo "  ║   open-source social utility bot       ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# Check Python version
PYTHON=""
for cmd in python3.11 python3.12 python3.13 python3; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | awk '{print $2}')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11+ is required but not found."
    echo "Install it from https://python.org"
    exit 1
fi

echo "Using $PYTHON ($($PYTHON --version))"

# Create virtual environment
if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    $PYTHON -m venv "$PROJECT_ROOT/.venv"
fi

source "$PROJECT_ROOT/.venv/bin/activate"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -e "$PROJECT_ROOT"

# Initialize git submodule
if [ ! -f "$PROJECT_ROOT/vendor/hermes-agent/README.md" ]; then
    echo ""
    echo "Initializing Hermes Agent submodule..."
    cd "$PROJECT_ROOT"
    git submodule update --init --recursive
fi

# Create data directories
mkdir -p "$PROJECT_ROOT/data/dossiers"
mkdir -p "$PROJECT_ROOT/data/chat"

# Run the Python setup wizard
echo ""
$PYTHON "$SCRIPT_DIR/setup_wizard.py"

echo ""
echo "Setup complete!"
echo ""
echo "To start the bot:"
echo "  ./scripts/start.sh"
echo ""
