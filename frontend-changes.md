# Frontend Changes

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
