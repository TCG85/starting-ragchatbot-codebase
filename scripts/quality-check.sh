#!/usr/bin/env bash
# Run all frontend quality checks. Exit non-zero if any check fails.
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

echo "--- Prettier format check ---"
npm run format:check

echo "--- ESLint ---"
npm run lint

echo "All checks passed."
