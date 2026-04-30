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
