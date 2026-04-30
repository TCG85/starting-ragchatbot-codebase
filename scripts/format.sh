#!/usr/bin/env bash
# Auto-format all frontend files with Prettier.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v npm &>/dev/null; then
    echo "Error: npm is not installed." >&2
    exit 1
fi

if [ ! -d node_modules ]; then
    echo "Installing dependencies..."
    npm install
fi

echo "Formatting frontend files..."
npm run format
echo "Done."
