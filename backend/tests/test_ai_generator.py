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


def test_second_api_call_has_no_tools_parameter(generator, mock_anthropic):
    """Second call must not include 'tools' — avoids infinite tool loop."""
    tool_block = _make_tool_block("search_course_content", {"query": "x"})
    mock_anthropic.messages.create.side_effect = [
        _make_response("tool_use", tool_blocks=[tool_block]),
        _make_response("end_turn", text="answer"),
    ]
    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "result"

    generator.generate_response(
        query="q", tools=[{"name": "search_course_content"}], tool_manager=tool_manager
    )

    second_call_kwargs = mock_anthropic.messages.create.call_args_list[1][1]
    assert "tools" not in second_call_kwargs


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
