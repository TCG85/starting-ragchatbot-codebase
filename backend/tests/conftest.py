import sys
import os

# Make backend/ importable from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import tempfile
from models import Course, Lesson, CourseChunk
from vector_store import VectorStore


@pytest.fixture
def tmp_chroma_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def seeded_vector_store(tmp_chroma_path):
    """Real VectorStore (temp ChromaDB) with one course and several content chunks."""
    store = VectorStore(tmp_chroma_path, "all-MiniLM-L6-v2", max_results=5)

    course = Course(
        title="MCP Course",
        course_link="https://example.com/mcp",
        instructor="Jane Doe",
        lessons=[
            Lesson(lesson_number=1, title="Intro to MCP", lesson_link="https://example.com/mcp/1"),
            Lesson(lesson_number=5, title="Advanced MCP", lesson_link="https://example.com/mcp/5"),
        ],
    )
    store.add_course_metadata(course)

    chunks = [
        CourseChunk(
            content="MCP stands for Model Context Protocol and enables tool use.",
            course_title="MCP Course",
            lesson_number=1,
            chunk_index=0,
        ),
        CourseChunk(
            content="Advanced MCP covers server transports and authentication flows.",
            course_title="MCP Course",
            lesson_number=5,
            chunk_index=1,
        ),
    ]
    store.add_course_content(chunks)
    return store
