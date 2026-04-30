"""
Tests for the FastAPI endpoints defined in app.py.

A minimal test app is built here (not imported from app.py) to avoid the
module-level side effects in app.py: RAGSystem(config) initialisation and
StaticFiles mount that require a real frontend/ directory on disk.

The test app replicates the route logic and Pydantic models verbatim so the
tests exercise the same HTTP contract without those environment dependencies.
"""

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import List, Optional


# ---------------------------------------------------------------------------
# Pydantic models — mirrors app.py
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class Source(BaseModel):
    text: str
    url: str


class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]
    session_id: str


class CourseStats(BaseModel):
    total_courses: int
    course_titles: List[str]


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def _make_app(rag) -> FastAPI:
    """Return a FastAPI app wired to the provided RAGSystem mock."""
    app = FastAPI()

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id or rag.session_manager.create_session()
            answer, sources = rag.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = rag.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/session/{session_id}")
    async def delete_session(session_id: str):
        rag.session_manager.delete_session(session_id)
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(mock_rag_system):
    return TestClient(_make_app(mock_rag_system))


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------

def test_query_returns_200(client):
    resp = client.post("/api/query", json={"query": "What is MCP?"})
    assert resp.status_code == 200


def test_query_response_shape(client):
    resp = client.post("/api/query", json={"query": "What is MCP?"})
    body = resp.json()
    assert "answer" in body
    assert "sources" in body
    assert "session_id" in body


def test_query_returns_rag_answer(client, mock_rag_system):
    mock_rag_system.query.return_value = ("MCP stands for Model Context Protocol.", [])
    resp = client.post("/api/query", json={"query": "What is MCP?"})
    assert resp.json()["answer"] == "MCP stands for Model Context Protocol."


def test_query_without_session_id_creates_session(client, mock_rag_system):
    mock_rag_system.session_manager.create_session.return_value = "new-sess"
    resp = client.post("/api/query", json={"query": "question"})
    assert resp.json()["session_id"] == "new-sess"
    mock_rag_system.session_manager.create_session.assert_called_once()


def test_query_with_session_id_reuses_it(client, mock_rag_system):
    resp = client.post("/api/query", json={"query": "follow-up", "session_id": "existing-sess"})
    assert resp.json()["session_id"] == "existing-sess"
    mock_rag_system.session_manager.create_session.assert_not_called()


def test_query_passes_query_text_to_rag(client, mock_rag_system):
    client.post("/api/query", json={"query": "Tell me about agents"})
    call_args = mock_rag_system.query.call_args
    assert call_args[0][0] == "Tell me about agents"


def test_query_includes_sources_in_response(client, mock_rag_system):
    mock_rag_system.query.return_value = (
        "Answer with sources",
        [{"text": "MCP Course - Lesson 1", "url": "https://example.com/1"}],
    )
    resp = client.post("/api/query", json={"query": "question"})
    sources = resp.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["text"] == "MCP Course - Lesson 1"


def test_query_returns_500_on_rag_error(client, mock_rag_system):
    mock_rag_system.query.side_effect = RuntimeError("DB unavailable")
    resp = client.post("/api/query", json={"query": "question"})
    assert resp.status_code == 500
    assert "DB unavailable" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/courses
# ---------------------------------------------------------------------------

def test_courses_returns_200(client):
    resp = client.get("/api/courses")
    assert resp.status_code == 200


def test_courses_response_shape(client):
    resp = client.get("/api/courses")
    body = resp.json()
    assert "total_courses" in body
    assert "course_titles" in body


def test_courses_returns_analytics_from_rag(client, mock_rag_system):
    mock_rag_system.get_course_analytics.return_value = {
        "total_courses": 3,
        "course_titles": ["A", "B", "C"],
    }
    resp = client.get("/api/courses")
    body = resp.json()
    assert body["total_courses"] == 3
    assert body["course_titles"] == ["A", "B", "C"]


def test_courses_returns_500_on_rag_error(client, mock_rag_system):
    mock_rag_system.get_course_analytics.side_effect = RuntimeError("analytics broken")
    resp = client.get("/api/courses")
    assert resp.status_code == 500
    assert "analytics broken" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/session/{session_id}
# ---------------------------------------------------------------------------

def test_delete_session_returns_200(client):
    resp = client.delete("/api/session/sess-abc")
    assert resp.status_code == 200


def test_delete_session_response_body(client):
    resp = client.delete("/api/session/sess-abc")
    assert resp.json() == {"status": "ok"}


def test_delete_session_calls_session_manager(client, mock_rag_system):
    client.delete("/api/session/my-session-id")
    mock_rag_system.session_manager.delete_session.assert_called_once_with("my-session-id")
