"""
Tests for AIGenerator in ai_generator.py.

All tests mock anthropic.Anthropic so no real API calls are made.
They verify:
  - Direct (no-tool) response path
  - Tool-use path: tool invoked, result passed in second call, answer synthesized
  - Conversation history wired into system prompt
  - Error strings from tool execution reach the second Claude call
    (explaining why the user sees "I wasn't able to retrieve...")
"""

import pytest
from unittest.mock import MagicMock, patch, call
from ai_generator import AIGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_anthropic():
    with patch("ai_generator.anthropic.Anthropic") as cls:
        yield cls.return_value


@pytest.fixture
def generator(mock_anthropic):
    return AIGenerator(api_key="test-key", model="claude-sonnet-4-6")


def _make_response(stop_reason, text=None, tool_blocks=None):
    """Build a minimal mock Anthropic response."""
    resp = MagicMock()
    resp.stop_reason = stop_reason
    if stop_reason == "end_turn":
        block = MagicMock()
        block.text = text
        resp.content = [block]
    else:
        resp.content = tool_blocks or []
    return resp


def _make_tool_block(name, input_dict, tool_id="tu_001"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.id = tool_id
    block.input = input_dict
    return block


# ---------------------------------------------------------------------------
# Direct response (no tool use)
# ---------------------------------------------------------------------------

def test_direct_response_returns_content_text(generator, mock_anthropic):
    mock_anthropic.messages.create.return_value = _make_response("end_turn", text="42")

    result = generator.generate_response(query="What is 6 × 7?")

    assert result == "42"
    mock_anthropic.messages.create.assert_called_once()


def test_direct_response_does_not_call_tool_manager(generator, mock_anthropic):
    mock_anthropic.messages.create.return_value = _make_response("end_turn", text="answer")
    tool_manager = MagicMock()

    generator.generate_response(query="general question", tool_manager=tool_manager)

    tool_manager.execute_tool.assert_not_called()


# ---------------------------------------------------------------------------
# Tool-use path
# ---------------------------------------------------------------------------

def test_tool_use_triggers_execute_tool(generator, mock_anthropic):
    tool_block = _make_tool_block(
        "search_course_content", {"query": "MCP lesson 5", "course_name": "MCP", "lesson_number": 5}
    )
    first = _make_response("tool_use", tool_blocks=[tool_block])
    second = _make_response("end_turn", text="Lesson 5 covers authentication.")
    mock_anthropic.messages.create.side_effect = [first, second]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "[MCP Course - Lesson 5]\nAuthentication flows..."

    result = generator.generate_response(
        query="What is in lesson 5?",
        tools=[{"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    tool_manager.execute_tool.assert_called_once_with(
        "search_course_content",
        query="MCP lesson 5",
        course_name="MCP",
        lesson_number=5,
    )
    assert result == "Lesson 5 covers authentication."


def test_tool_use_makes_two_api_calls(generator, mock_anthropic):
    tool_block = _make_tool_block("search_course_content", {"query": "MCP"})
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block]),
        _make_response("end_turn", text="Final answer"),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "some content"

    generator.generate_response(
        query="Tell me about MCP",
        tools=[{"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    assert mock_anthropic.messages.create.call_count == 2


def test_tool_result_included_in_second_api_call(generator, mock_anthropic):
    tool_block = _make_tool_block("search_course_content", {"query": "MCP"}, tool_id="tu_999")
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block]),
        _make_response("end_turn", text="Synthesized"),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "Tool output text"

    generator.generate_response(
        query="About MCP",
        tools=[{"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    second_call_kwargs = mock_anthropic.messages.create.call_args_list[1][1]
    messages = second_call_kwargs["messages"]
    # Last message is the user message carrying tool results
    last_message = messages[-1]
    assert last_message["role"] == "user"
    content = last_message["content"]
    tool_result_block = next(
        (item for item in content if isinstance(item, dict) and item.get("type") == "tool_result"),
        None,
    )
    assert tool_result_block is not None
    assert tool_result_block["tool_use_id"] == "tu_999"
    assert tool_result_block["content"] == "Tool output text"


def test_synthesis_instruction_appended_to_tool_result_message(generator, mock_anthropic):
    tool_block = _make_tool_block("search_course_content", {"query": "MCP"})
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block]),
        _make_response("end_turn", text="Done"),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "content"

    generator.generate_response(
        query="question", tools=[{}], tool_manager=tool_manager
    )

    second_call_kwargs = mock_anthropic.messages.create.call_args_list[1][1]
    messages = second_call_kwargs["messages"]
    last_message = messages[-1]
    text_blocks = [
        item for item in last_message["content"]
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    assert any("answer" in b["text"].lower() or "question" in b["text"].lower() for b in text_blocks)


def test_synthesis_call_after_max_rounds_has_no_tools(generator, mock_anthropic):
    """Synthesis call after max_rounds must not include 'tools' — avoids infinite tool loop."""
    tool_block1 = _make_tool_block("search_course_content", {"query": "x"}, "tu_001")
    tool_block2 = _make_tool_block("get_course_outline", {"course_name": "c"}, "tu_002")
    tool_block3 = _make_tool_block("search_course_content", {"query": "y"}, "tu_003")
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block1]),
        _make_response("tool_use", tool_blocks=[tool_block2]),
        _make_response("tool_use", tool_blocks=[tool_block3]),
        _make_response("end_turn", text="final answer"),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "result"

    generator.generate_response(
        query="q", tools=[{"name": "search_course_content"}], tool_manager=tool_manager
    )

    synthesis_call_kwargs = mock_anthropic.messages.create.call_args_list[3][1]
    assert "tools" not in synthesis_call_kwargs


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

def test_conversation_history_included_in_system_prompt(generator, mock_anthropic):
    mock_anthropic.messages.create.return_value = _make_response("end_turn", text="ok")

    generator.generate_response(
        query="follow-up",
        conversation_history="User: first question\nAssistant: first answer",
    )

    call_kwargs = mock_anthropic.messages.create.call_args[1]
    assert "first question" in call_kwargs["system"]
    assert "first answer" in call_kwargs["system"]


def test_no_conversation_history_uses_base_prompt(generator, mock_anthropic):
    mock_anthropic.messages.create.return_value = _make_response("end_turn", text="ok")

    generator.generate_response(query="standalone question", conversation_history=None)

    call_kwargs = mock_anthropic.messages.create.call_args[1]
    assert "Previous conversation" not in call_kwargs["system"]


# ---------------------------------------------------------------------------
# Error propagation — explains the "I wasn't able to retrieve" symptom
# ---------------------------------------------------------------------------

def test_search_error_string_reaches_second_api_call(generator, mock_anthropic):
    """
    When CourseSearchTool.execute() returns 'Search error: n_results < 1'
    (caused by MAX_RESULTS=0), that string is passed as the tool_result content
    in the second API call. Claude then generates a message like
    'I wasn't able to retrieve the content due to a search error.'

    This test confirms the error string flows from the tool through to Claude.
    """
    error_payload = "Search error: Number of requested results 0 is less than number of elements in index"

    tool_block = _make_tool_block(
        "search_course_content",
        {"query": "lesson 5 of the MCP course"},
        tool_id="tu_error",
    )
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block]),
        _make_response("end_turn", text="I wasn't able to retrieve the content due to a search error."),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = error_payload

    result = generator.generate_response(
        query="What is in lesson 5 of the MCP course?",
        tools=[{"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    # Confirm error string was in the second call's messages
    second_call_kwargs = mock_anthropic.messages.create.call_args_list[1][1]
    messages = second_call_kwargs["messages"]
    last_message = messages[-1]
    tool_result_block = next(
        item for item in last_message["content"]
        if isinstance(item, dict) and item.get("type") == "tool_result"
    )
    assert error_payload in tool_result_block["content"]

    # And Claude's response reflects the error
    assert "wasn't able" in result or "error" in result.lower()


# ---------------------------------------------------------------------------
# Sequential tool calling (multi-round agentic loop)
# ---------------------------------------------------------------------------

def test_sequential_two_rounds_makes_three_api_calls(generator, mock_anthropic):
    tool_block1 = _make_tool_block("get_course_outline", {"course_name": "MCP"}, "tu_001")
    tool_block2 = _make_tool_block("search_course_content", {"query": "MCP lesson 4"}, "tu_002")
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block1]),
        _make_response("tool_use", tool_blocks=[tool_block2]),
        _make_response("end_turn", text="Here is the combined answer."),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "some content"

    result = generator.generate_response(
        query="What topic does lesson 4 of the MCP course cover?",
        tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    assert mock_anthropic.messages.create.call_count == 3
    assert result == "Here is the combined answer."


def test_sequential_two_rounds_executes_both_tools(generator, mock_anthropic):
    tool_block1 = _make_tool_block("get_course_outline", {"course_name": "MCP"}, "tu_001")
    tool_block2 = _make_tool_block("search_course_content", {"query": "agents"}, "tu_002")
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block1]),
        _make_response("tool_use", tool_blocks=[tool_block2]),
        _make_response("end_turn", text="Done."),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = ["outline result", "search result"]

    generator.generate_response(
        query="multi-tool query",
        tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    assert tool_manager.execute_tool.call_count == 2
    tool_manager.execute_tool.assert_any_call("get_course_outline", course_name="MCP")
    tool_manager.execute_tool.assert_any_call("search_course_content", query="agents")


def test_sequential_final_synthesis_call_has_no_tools_two_rounds(generator, mock_anthropic):
    """When loop exits after max_rounds, synthesis call must not include tools."""
    tool_block1 = _make_tool_block("get_course_outline", {"course_name": "MCP"}, "tu_001")
    tool_block2 = _make_tool_block("search_course_content", {"query": "lesson 4"}, "tu_002")
    tool_block3 = _make_tool_block("search_course_content", {"query": "related"}, "tu_003")
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block1]),
        _make_response("tool_use", tool_blocks=[tool_block2]),
        _make_response("tool_use", tool_blocks=[tool_block3]),
        _make_response("end_turn", text="Synthesized answer."),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "content"

    generator.generate_response(
        query="q",
        tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    synthesis_kwargs = mock_anthropic.messages.create.call_args_list[3][1]
    assert "tools" not in synthesis_kwargs


def test_max_rounds_capped_at_two(generator, mock_anthropic):
    """Loop stops after 2 rounds even if Claude keeps requesting tool_use."""
    tool_block1 = _make_tool_block("search_course_content", {"query": "q1"}, "tu_001")
    tool_block2 = _make_tool_block("search_course_content", {"query": "q2"}, "tu_002")
    tool_block3 = _make_tool_block("search_course_content", {"query": "q3"}, "tu_003")
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block1]),
        _make_response("tool_use", tool_blocks=[tool_block2]),
        _make_response("tool_use", tool_blocks=[tool_block3]),
        _make_response("end_turn", text="Final synthesized answer."),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "some result"

    result = generator.generate_response(
        query="complex query",
        tools=[{"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    assert mock_anthropic.messages.create.call_count == 4
    assert tool_manager.execute_tool.call_count == 3
    assert result == "Final synthesized answer."


def test_single_round_tool_use_regression(generator, mock_anthropic):
    """Single-round path: loop exits on end_turn with no extra synthesis call."""
    tool_block = _make_tool_block("search_course_content", {"query": "MCP"}, "tu_001")
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block]),
        _make_response("end_turn", text="Direct answer from loop."),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "search content"

    result = generator.generate_response(
        query="Tell me about MCP",
        tools=[{"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    assert mock_anthropic.messages.create.call_count == 2
    assert result == "Direct answer from loop."


def test_tool_error_mid_loop_reaches_synthesis(generator, mock_anthropic):
    """A tool execution error becomes string content passed to Claude, not an exception."""
    tool_block = _make_tool_block("search_course_content", {"query": "MCP"}, "tu_err")
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block]),
        _make_response("end_turn", text="I wasn't able to retrieve the content."),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = RuntimeError("DB unavailable")

    result = generator.generate_response(
        query="What is MCP?",
        tools=[{"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    assert mock_anthropic.messages.create.call_count == 2

    second_call_kwargs = mock_anthropic.messages.create.call_args_list[1][1]
    messages = second_call_kwargs["messages"]
    last_message = messages[-1]
    tool_result_block = next(
        item for item in last_message["content"]
        if isinstance(item, dict) and item.get("type") == "tool_result"
    )
    assert "DB unavailable" in tool_result_block["content"]
    assert "wasn't able" in result or "error" in result.lower()
