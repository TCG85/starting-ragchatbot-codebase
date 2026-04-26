# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the application

Requires a `.env` file in the project root:
```
ANTHROPIC_API_KEY=your_key_here
```

**Before starting the server**, verify both models in `backend/config.py` are valid:

1. **`ANTHROPIC_MODEL`** — must be a current Anthropic model ID. Valid options (as of 2026-04):
   - `claude-opus-4-7`
   - `claude-sonnet-4-6` (default)
   - `claude-haiku-4-5-20251001`
   If the model returns a 404 from the API, update it to the latest Sonnet model and inform the user.

2. **`EMBEDDING_MODEL`** — must be a valid `sentence-transformers` model name (e.g. `all-MiniLM-L6-v2`). Verify it can be loaded by running:
   ```bash
   cd backend && uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); print('OK')"
   ```
   If it fails, inform the user and suggest a valid replacement.

```bash
# Quick start
./run.sh

# Manual
cd backend
uv run uvicorn app:app --reload --port 8000
```

App runs at `http://localhost:8000`. The server serves the frontend as static files from `/`.

## Package management

Uses `uv`. Always use `uv` to run the server, run Python files, and manage all dependencies — never use `pip` directly.

To add/sync dependencies:
```bash
uv sync
uv add <package>
```

No test suite is currently configured.

## Architecture

This is a RAG chatbot with a FastAPI backend and a vanilla JS frontend. The backend is the only server — it serves both the API and the static frontend files.

**Query flow:**
1. Frontend (`frontend/script.js`) POSTs `{ query, session_id }` to `POST /api/query`
2. `app.py` delegates to `RAGSystem.query()`
3. `RAGSystem` fetches conversation history from `SessionManager`, then calls `AIGenerator`
4. `AIGenerator` makes a first Claude API call with the `search_course_content` tool available
5. If Claude invokes the tool, `ToolManager` → `CourseSearchTool` → `VectorStore` runs a semantic search against ChromaDB and returns formatted chunks
6. A second Claude API call synthesizes the search results into a final answer
7. Sources and response are returned to the frontend

**Document ingestion** runs on startup (`app.py` `startup_event`). It reads `.txt` files from `docs/`, parses them via `DocumentProcessor` into `Course`/`Lesson`/`CourseChunk` Pydantic models, and upserts them into two ChromaDB collections:
- `course_catalog` — course-level metadata for semantic course name resolution
- `course_content` — chunked lesson text for retrieval (800-char chunks, 100-char overlap)

Embeddings use `sentence-transformers/all-MiniLM-L6-v2` locally. The ChromaDB data is persisted to `backend/chroma_db/`.

**Course document format** (files in `docs/`):
```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 0: <title>
Lesson Link: <url>
<content...>
```

**Key config** (`backend/config.py`): model (`claude-sonnet-4-6`), chunk size, max search results (5), max conversation history (2 turns).

## Adding a new tool

1. Create a class extending `Tool` (ABC) in `backend/search_tools.py` with `get_tool_definition()` and `execute()` methods
2. Register it in `RAGSystem.__init__()` via `self.tool_manager.register_tool(...)`
