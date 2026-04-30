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

---

# API Endpoint Tests

No frontend files were modified. This feature added API endpoint testing infrastructure to the backend test suite.

## Changes made

### `pyproject.toml`
- Added `[tool.pytest.ini_options]` with `testpaths = ["backend/tests"]` and `pythonpath = ["backend"]` so `uv run pytest` works from the project root without flags.
- Added `httpx>=0.27` to dev dependencies (required by FastAPI's `TestClient`).

### `backend/tests/conftest.py`
- Added `from unittest.mock import MagicMock` import.
- Added `mock_rag_system` fixture: a pre-configured `MagicMock` of `RAGSystem` shared across all test files. Pre-sets sensible defaults for `create_session`, `query`, and `get_course_analytics`.

### `backend/tests/test_api_endpoints.py` (new file)
Tests for the three API endpoints (`POST /api/query`, `GET /api/courses`, `DELETE /api/session/{session_id}`).

The file builds its own minimal FastAPI test app (`_make_app`) rather than importing `app.py` directly, to avoid two module-level side effects in `app.py`:
1. `RAGSystem(config)` — would attempt real ChromaDB/Anthropic initialisation.
2. `StaticFiles(directory="../frontend")` — would crash because `frontend/` does not exist relative to the test working directory.

The test app replicates the route logic and Pydantic models verbatim so the HTTP contract is fully exercised. 15 tests cover status codes, response shapes, mock delegation, session handling, source propagation, and 500 error paths.

---

# Frontend Changes: Dark/Light Theme Toggle

## Summary

Added a dark/light theme toggle button that lets users switch between the existing dark theme and a new light theme. The preference is persisted across page reloads via `localStorage`.

---

## Files Changed

### `frontend/index.html`
- Added a `<button id="themeToggle">` element as the first child of `<body>`, positioned fixed to the top-right corner.
- Button contains two inline SVGs: `.icon-sun` (shown in dark mode) and `.icon-moon` (shown in light mode).
- Button has `aria-label="Toggle theme"` and `title` for accessibility and keyboard navigation.
- Bumped CSS and JS cache-busting versions from `?v=10` to `?v=11`.

### `frontend/style.css`

**New CSS variables block `[data-theme="light"]`** — overrides the dark-mode `:root` variables:
| Variable | Dark | Light |
|---|---|---|
| `--background` | `#0f172a` | `#f8fafc` |
| `--surface` | `#1e293b` | `#ffffff` |
| `--surface-hover` | `#334155` | `#f1f5f9` |
| `--text-primary` | `#f1f5f9` | `#0f172a` |
| `--text-secondary` | `#94a3b8` | `#475569` |
| `--border-color` | `#334155` | `#e2e8f0` |
| `--code-bg` | `rgba(0,0,0,0.2)` | `rgba(0,0,0,0.06)` |
| `--source-tag-color` | `#93c5fd` | `#1d4ed8` |
| `--toggle-bg` | `#1e293b` | `#ffffff` |

**Smooth transitions** — added a `*, *::before, *::after` rule with `transition` on `background-color`, `color`, `border-color`, and `box-shadow` (0.25s ease) so all elements animate when switching themes.

**Replaced hardcoded colors** — `source-tag` and `code`/`pre` backgrounds previously used hardcoded `rgba` values; these now use the new CSS variables (`--source-tag-*`, `--code-bg`) so they adapt correctly in light mode.

**`.theme-toggle` button styles** — fixed-position circular button (40×40px, border-radius 50%), using new `--toggle-*` variables for background, border, and icon color. Includes `:hover` (highlights with `--primary-color`) and `:focus` (3px focus ring using `--focus-ring`) states.

**Icon visibility logic:**
```css
/* Default (dark mode): hide moon, show sun */
.icon-moon { display: none; }

/* Light mode: hide sun, show moon */
[data-theme="light"] .icon-sun { display: none; }
[data-theme="light"] .icon-moon { display: block; }
```
The `[data-theme="light"]` selector has higher specificity (0,2,0) than the base `.icon-moon` rule (0,1,0), ensuring the correct icon shows in each mode.

### `frontend/script.js`

Added two functions before the `DOMContentLoaded` listener:

- **`initTheme()`** — runs immediately on script load (before first paint) to read `localStorage` and set `data-theme="light"` on `document.documentElement` if the user previously chose light mode. This prevents a flash of the wrong theme.
- **`toggleTheme()`** — reads the current `data-theme` attribute, toggles it, and saves the new preference to `localStorage`.

Wired `toggleTheme` to the button's `click` event inside `DOMContentLoaded`.
