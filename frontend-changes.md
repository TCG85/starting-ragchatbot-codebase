# Frontend Code Quality Changes

## Overview

Added frontend code quality tooling (Prettier + ESLint) to enforce consistent formatting across all frontend files (`frontend/*.js`, `frontend/*.html`, `frontend/*.css`).

## Files Added

### `package.json`
Node.js project manifest with npm scripts for quality checks:
- `npm run format` — auto-format all frontend files with Prettier
- `npm run format:check` — check formatting without modifying files (CI-safe)
- `npm run lint` — run ESLint on `frontend/script.js`
- `npm run lint:fix` — auto-fix ESLint violations
- `npm run quality` — run format check and lint together

Dev dependencies: `prettier@^3`, `eslint@^9`.

### `.prettierrc.json`
Prettier configuration matching the existing code style:
- 4-space indentation
- Single quotes in JS
- Semicolons on
- 100-character print width
- `es5` trailing commas
- LF line endings

### `.prettierignore`
Excludes `node_modules/`, `backend/`, `docs/`, and lock files from Prettier.

### `eslint.config.js`
Flat ESLint config (v9+) targeting `frontend/**/*.js`:
- Browser globals declared (`document`, `window`, `fetch`, `marked`, etc.)
- `no-var` enforced — use `let`/`const`
- `eqeqeq` enforced — use `===`
- `no-undef` as error, `no-unused-vars` and `prefer-const` as warnings

### `scripts/format.sh`
Shell script that installs deps if needed and runs `npm run format`.

### `scripts/quality-check.sh`
Shell script that installs deps if needed and runs Prettier check + ESLint. Exits non-zero on failure — suitable for use in CI or a pre-commit hook.

## Files Modified

### `frontend/script.js`
- Removed extraneous blank line between `setupEventListeners` and `sendMessage` to match single-blank-line separator convention enforced by Prettier.

## Usage

```bash
# Install dev dependencies (one-time)
npm install

# Format all frontend files
npm run format
# or
./scripts/format.sh

# Check formatting without modifying files
npm run format:check

# Run all quality checks
./scripts/quality-check.sh
```
