"""
Tests for RAGSystem.query() in rag_system.py.

Uses a real (temp) VectorStore + seeded ChromaDB data.
Mocks anthropic.Anthropic so no real API calls are made.
"""

import pytest
from unittest.mock import MagicMock, patch
from rag_system import RAGSystem
from models import Course, Lesson, CourseChunk


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

def make_config(chroma_path, max_results=5):
    cfg = MagicMock()
    cfg.ANTHROPIC_API_KEY = "test-key"
    cfg.ANTHROPIC_MODEL = "claude-sonnet-4-6"
    cfg.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    cfg.CHUNK_SIZE = 800
    cfg.CHUNK_OVERLAP = 100
    cfg.MAX_RESULTS = max_results
    cfg.MAX_HISTORY = 2
    cfg.CHROMA_PATH = chroma_path
    return cfg


def _end_turn_response(text):
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    block = MagicMock()
    block.text = text
    resp.content = [block]
    return resp


def _tool_use_response(tool_name, tool_input, tool_id="tu_001"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.id = tool_id
    block.input = tool_input
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


# ---------------------------------------------------------------------------
# Basic query contract
# ---------------------------------------------------------------------------

def test_query_returns_string_and_list(tmp_chroma_path):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _end_turn_response("Answer text")
        system = RAGSystem(make_config(tmp_chroma_path))
        result = system.query("What is 2 + 2?")

    assert isinstance(result, tuple)
    response, sources = result
    assert isinstance(response, str)
    assert isinstance(sources, list)


def test_query_direct_answer_no_tool_use(tmp_chroma_path):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _end_turn_response(
            "Python is a programming language."
        )
        system = RAGSystem(make_config(tmp_chroma_path))
        response, sources = system.query("What is Python?")

    assert response == "Python is a programming language."
    assert sources == []


# ---------------------------------------------------------------------------
# Tool-use flow
# ---------------------------------------------------------------------------

def test_query_tool_use_makes_two_api_calls(tmp_chroma_path):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "MCP lesson 5"}),
            _end_turn_response("Lesson 5 is about advanced MCP topics."),
        ]
        system = RAGSystem(make_config(tmp_chroma_path))
        response, _ = system.query("What is in lesson 5 of the MCP course?")

    assert response == "Lesson 5 is about advanced MCP topics."
    assert client.messages.create.call_count == 2


def test_query_tool_use_passes_tool_definitions_to_ai(tmp_chroma_path):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = _end_turn_response("answer")
        system = RAGSystem(make_config(tmp_chroma_path))
        system.query("question")

    first_call_kwargs = client.messages.create.call_args[1]
    assert "tools" in first_call_kwargs
    tool_names = [t["name"] for t in first_call_kwargs["tools"]]
    assert "search_course_content" in tool_names


def test_query_sources_populated_after_tool_use(seeded_vector_store, tmp_chroma_path):
    """When search_course_content runs and finds results, sources are non-empty."""
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.side_effect = [
            _tool_use_response(
                "search_course_content",
                {"query": "MCP protocol", "course_name": "MCP"},
            ),
            _end_turn_response("MCP is a protocol."),
        ]
        cfg = make_config(tmp_chroma_path)
        system = RAGSystem(cfg)
        # Replace freshly-created vector_store with our seeded one
        system.vector_store = seeded_vector_store
        system.search_tool.store = seeded_vector_store

        _, sources = system.query("Tell me about MCP.")

    assert len(sources) > 0
    assert any("MCP Course" in s["text"] for s in sources)


# ---------------------------------------------------------------------------
# Session history
# ---------------------------------------------------------------------------

def test_query_saves_exchange_to_session(tmp_chroma_path):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _end_turn_response("Session answer")
        system = RAGSystem(make_config(tmp_chroma_path))
        system.query("Session question", session_id="sess-1")

    history = system.session_manager.get_conversation_history("sess-1")
    assert history is not None
    assert "Session question" in history
    assert "Session answer" in history


def test_query_without_session_id_does_not_crash(tmp_chroma_path):
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _end_turn_response("ok")
        system = RAGSystem(make_config(tmp_chroma_path))
        response, _ = system.query("anonymous query")

    assert response == "ok"


# ---------------------------------------------------------------------------
# Regression: MAX_RESULTS=0 end-to-end
# ---------------------------------------------------------------------------

def test_regression_zero_max_results_end_to_end(tmp_chroma_path):
    """
    End-to-end regression: when config.MAX_RESULTS=0, the search tool returns a
    'Search error: ...' string that Claude receives as the tool result, causing it to
    report 'I wasn't able to retrieve the content due to a search error.'

    This test simulates Claude calling search_course_content, then inspects the
    tool_result that is fed back to Claude in the second API call.

    FAILS when config.MAX_RESULTS = 0  (tool output is a 'Search error:' string)
    PASSES when config.MAX_RESULTS = 5  (tool output is real course content)
    """
    from config import config
    from models import Course, Lesson

    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "search_course_content"
        tool_block.id = "tu_regression"
        tool_block.input = {"query": "lesson 5 content", "course_name": "MCP Course", "lesson_number": 5}

        first_resp = MagicMock()
        first_resp.stop_reason = "tool_use"
        first_resp.content = [tool_block]

        second_resp = _end_turn_response("Here is what lesson 5 covers.")
        client.messages.create.side_effect = [first_resp, second_resp]

        # Use the real config.MAX_RESULTS to reproduce production behaviour
        system = RAGSystem(make_config(tmp_chroma_path, max_results=config.MAX_RESULTS))

        # Seed BOTH course metadata (for name resolution) and content chunks
        course = Course(
            title="MCP Course",
            course_link="https://example.com/mcp",
            instructor="Jane Doe",
            lessons=[Lesson(lesson_number=5, title="Advanced MCP", lesson_link="https://example.com/mcp/5")],
        )
        system.vector_store.add_course_metadata(course)
        system.vector_store.add_course_content([
            CourseChunk(
                content="Advanced MCP covers server transports and authentication flows.",
                course_title="MCP Course",
                lesson_number=5,
                chunk_index=0,
            )
        ])

        system.query("What is covered in lesson 5 of the MCP course?")

    assert client.messages.create.call_count == 2, "Expected two API calls (initial + after tool)"

    second_call_kwargs = client.messages.create.call_args_list[1][1]
    messages = second_call_kwargs["messages"]
    last_message = messages[-1]
    tool_result_block = next(
        (item for item in last_message["content"]
         if isinstance(item, dict) and item.get("type") == "tool_result"),
        None,
    )

    assert tool_result_block is not None, "No tool_result block in second API call"
    tool_output = tool_result_block["content"]

    assert "error" not in tool_output.lower(), (
        f"Search tool returned an error with MAX_RESULTS={config.MAX_RESULTS}: {tool_output!r}\n"
        "Fix: change MAX_RESULTS from 0 to 5 in backend/config.py"
    )
    assert "No course found" not in tool_output, (
        f"Course name resolution failed: {tool_output!r}"
    )
