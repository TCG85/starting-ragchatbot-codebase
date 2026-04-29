import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Search Tool Usage:
- Use `search_course_content` **only** for questions about specific course content or detailed educational materials
- **Up to two sequential tool calls per query** — use a second call only when the first result is insufficient to answer the question completely
- Do not call the same tool twice with the same arguments
- Synthesize search results into accurate, fact-based responses
- If search yields no results, state this clearly without offering alternatives

Outline Tool Usage:
- Use `get_course_outline` for questions about course structure, lesson list, or course overview
- Returns: course title, course link, and the number and title of each lesson

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course content questions**: Use `search_course_content` first, then answer
- **Course outline/structure questions**: Use `get_course_outline` first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 2048
        }

    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        # Prepare API call parameters efficiently
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content
        }

        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}

        # Get response from Claude
        response = self.client.messages.create(**api_params)

        # Handle tool execution if needed
        if response.stop_reason == "tool_use" and tool_manager:
            return self._run_agentic_loop(response, api_params, tool_manager)

        # Return direct response
        return response.content[0].text

    def _run_agentic_loop(self, initial_response, base_params: Dict[str, Any],
                          tool_manager, max_rounds: int = 2) -> str:
        """
        Run an agentic loop allowing Claude up to max_rounds sequential tool calls.

        Each iteration keeps tools available so Claude can chain calls. The loop
        exits early when Claude returns end_turn; when max_rounds is exhausted
        with tool_use still active, a final synthesis call without tools is made.
        """
        messages = base_params["messages"].copy()
        current_response = initial_response
        rounds = 0

        while current_response.stop_reason == "tool_use" and rounds < max_rounds:
            # Append assistant's tool-use content to conversation
            messages.append({"role": "assistant", "content": current_response.content})

            # Execute all tool calls in this response
            tool_results = []
            for content_block in current_response.content:
                if content_block.type == "tool_use":
                    try:
                        tool_result = tool_manager.execute_tool(
                            content_block.name,
                            **content_block.input
                        )
                    except Exception as e:
                        tool_result = f"Tool execution error: {e}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": content_block.id,
                        "content": tool_result
                    })

            if not tool_results:
                break

            messages.append({"role": "user", "content": tool_results + [
                {"type": "text", "text": "Please answer the original question using the search results above."}
            ]})

            # Keep tools available so Claude can make a second sequential call
            loop_params = {
                **self.base_params,
                "messages": messages,
                "system": base_params["system"],
                "tools": base_params["tools"],
                "tool_choice": {"type": "auto"},
            }
            current_response = self.client.messages.create(**loop_params)
            rounds += 1

        # Claude finished naturally — return this response directly, no synthesis needed
        if current_response.stop_reason != "tool_use":
            if not current_response.content:
                return "I found relevant content but was unable to generate a response. Please try rephrasing your question."
            return current_response.content[0].text

        # max_rounds exhausted with tool_use still active — execute remaining tools
        # and force a final synthesis call without tools
        messages.append({"role": "assistant", "content": current_response.content})
        tool_results = []
        for content_block in current_response.content:
            if content_block.type == "tool_use":
                try:
                    tool_result = tool_manager.execute_tool(
                        content_block.name,
                        **content_block.input
                    )
                except Exception as e:
                    tool_result = f"Tool execution error: {e}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block.id,
                    "content": tool_result
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results + [
                {"type": "text", "text": "Please answer the original question using the search results above."}
            ]})

        synthesis_params = {
            **self.base_params,
            "messages": messages,
            "system": base_params["system"],
        }
        final_response = self.client.messages.create(**synthesis_params)
        if not final_response.content:
            return "I found relevant content but was unable to generate a response. Please try rephrasing your question."
        return final_response.content[0].text
