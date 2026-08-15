"""Tests for the routes exposed by the 'base' blueprint."""


def test_index_returns_ok(client):
    """The index route should respond with HTTP 200."""
    response = client.get("/")
    assert response.status_code == 200


def test_index_renders_html(client):
    """The index route should return HTML content."""
    response = client.get("/")
    assert "text/html" in response.content_type
