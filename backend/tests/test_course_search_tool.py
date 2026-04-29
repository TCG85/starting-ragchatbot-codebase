"""
Tests for CourseSearchTool.execute() in search_tools.py.

Unit tests use a mocked VectorStore so they are fast and isolated.
The regression test at the bottom uses a real (temp) VectorStore to
prove that MAX_RESULTS=0 causes every search to return an error string.
"""

import pytest
from unittest.mock import MagicMock
from search_tools import CourseSearchTool
from vector_store import SearchResults, VectorStore
from models import CourseChunk


# ---------------------------------------------------------------------------
# Unit tests — VectorStore is mocked
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_store():
    return MagicMock(spec=VectorStore)


@pytest.fixture
def tool(mock_store):
    return CourseSearchTool(mock_store)


def test_execute_returns_formatted_results(tool, mock_store):
    mock_store.search.return_value = SearchResults(
        documents=["MCP stands for Model Context Protocol."],
        metadata=[{"course_title": "MCP Course", "lesson_number": 5}],
        distances=[0.1],
    )
    mock_store.get_lesson_link.return_value = "https://example.com/mcp/5"

    result = tool.execute(query="what is MCP?", course_name="MCP", lesson_number=5)

    assert "MCP Course" in result
    assert "Lesson 5" in result
    assert "MCP stands for Model Context Protocol." in result


def test_execute_propagates_search_error(tool, mock_store):
    mock_store.search.return_value = SearchResults.empty(
        "Search error: Number of requested results 0 is less than number of elements in index"
    )

    result = tool.execute(query="what is MCP?")

    assert "Search error" in result


def test_execute_returns_no_content_message_when_empty(tool, mock_store):
    mock_store.search.return_value = SearchResults(
        documents=[], metadata=[], distances=[]
    )

    result = tool.execute(query="nonexistent topic")

    assert "No relevant content found" in result


def test_execute_no_content_message_includes_filters(tool, mock_store):
    mock_store.search.return_value = SearchResults(
        documents=[], metadata=[], distances=[]
    )

    result = tool.execute(query="test", course_name="MCP", lesson_number=5)

    assert "MCP" in result
    assert "5" in result


def test_execute_passes_query_and_filters_to_store(tool, mock_store):
    mock_store.search.return_value = SearchResults(
        documents=[], metadata=[], distances=[]
    )

    tool.execute(query="server transports", course_name="MCP", lesson_number=5)

    mock_store.search.assert_called_once_with(
        query="server transports", course_name="MCP", lesson_number=5
    )


def test_execute_passes_none_filters_when_omitted(tool, mock_store):
    mock_store.search.return_value = SearchResults(
        documents=[], metadata=[], distances=[]
    )

    tool.execute(query="general question")

    mock_store.search.assert_called_once_with(
        query="general question", course_name=None, lesson_number=None
    )


def test_execute_tracks_sources_after_successful_search(tool, mock_store):
    mock_store.search.return_value = SearchResults(
        documents=["Lesson content here."],
        metadata=[{"course_title": "MCP Course", "lesson_number": 5}],
        distances=[0.2],
    )
    mock_store.get_lesson_link.return_value = "https://example.com/mcp/5"

    tool.execute(query="test")

    assert len(tool.last_sources) == 1
    assert tool.last_sources[0]["text"] == "MCP Course - Lesson 5"
    assert tool.last_sources[0]["url"] == "https://example.com/mcp/5"


def test_execute_deduplicates_sources(tool, mock_store):
    mock_store.search.return_value = SearchResults(
        documents=["chunk 1", "chunk 2"],
        metadata=[
            {"course_title": "MCP Course", "lesson_number": 5},
            {"course_title": "MCP Course", "lesson_number": 5},
        ],
        distances=[0.1, 0.2],
    )
    mock_store.get_lesson_link.return_value = "https://example.com/mcp/5"

    tool.execute(query="test")

    assert len(tool.last_sources) == 1


def test_execute_clears_sources_on_error(tool, mock_store):
    # First call succeeds and sets sources
    mock_store.search.return_value = SearchResults(
        documents=["content"],
        metadata=[{"course_title": "MCP Course", "lesson_number": 1}],
        distances=[0.1],
    )
    mock_store.get_lesson_link.return_value = ""
    tool.execute(query="first query")
    assert len(tool.last_sources) == 1

    # Second call errors — sources should NOT be updated (error path returns early)
    mock_store.search.return_value = SearchResults.empty("Search error: something broke")
    tool.execute(query="second query")
    # last_sources stays from the previous call (error path returns before _format_results)
    assert len(tool.last_sources) == 1


# ---------------------------------------------------------------------------
# Regression tests — reproduce the MAX_RESULTS=0 bug using the real config
# ---------------------------------------------------------------------------

def test_regression_n_results_zero_raises_chroma_error(tmp_chroma_path):
    """
    Documents the failure mode: VectorStore with max_results=0 makes ChromaDB
    raise 'Number of requested results 0 is less than number of elements in index',
    which is caught and returned as a 'Search error: ...' string.
    This is exactly what gets sent to Claude, causing it to say
    'I wasn't able to retrieve the content due to a search error.'
    """
    store = VectorStore(tmp_chroma_path, "all-MiniLM-L6-v2", max_results=0)
    store.add_course_content([
        CourseChunk(
            content="MCP is a protocol for model-tool communication.",
            course_title="MCP Course",
            lesson_number=5,
            chunk_index=0,
        )
    ])
    tool = CourseSearchTool(store)
    # No course_name filter so course resolution is skipped; hits ChromaDB directly with n_results=0
    result = tool.execute(query="what is in lesson 5 of the MCP course?")
    assert "error" in result.lower(), f"Expected search error with max_results=0, got: {result!r}"


def test_regression_real_config_search_returns_content_not_error(seeded_vector_store, tmp_chroma_path):
    """
    Regression: search must return actual content when MAX_RESULTS is valid (> 0).
    Uses the real config.MAX_RESULTS value.

    FAILS when config.MAX_RESULTS = 0  (the bug — ChromaDB raises, error string returned)
    PASSES when config.MAX_RESULTS = 5  (the fix — real content returned)
    """
    from config import config
    from models import Course, Lesson

    # Build a fresh store using the actual configured max_results
    store = VectorStore(tmp_chroma_path, "all-MiniLM-L6-v2", max_results=config.MAX_RESULTS)
    course = Course(
        title="MCP Course",
        course_link="https://example.com/mcp",
        instructor="Jane Doe",
        lessons=[Lesson(lesson_number=5, title="Advanced MCP", lesson_link="https://example.com/mcp/5")],
    )
    store.add_course_metadata(course)
    store.add_course_content([
        CourseChunk(
            content="Advanced MCP covers server transports and authentication flows.",
            course_title="MCP Course",
            lesson_number=5,
            chunk_index=0,
        )
    ])

    tool = CourseSearchTool(store)
    result = tool.execute(query="what is in lesson 5 of the MCP course?", course_name="MCP")

    assert "error" not in result.lower(), (
        f"Search returned error with MAX_RESULTS={config.MAX_RESULTS}: {result!r}\n"
        "Fix: change MAX_RESULTS from 0 to 5 in backend/config.py"
    )
    assert "No course found" not in result
    assert len(result) > 0
