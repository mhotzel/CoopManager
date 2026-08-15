"""Shared pytest fixtures for the CoopManager test suite."""

import pytest

from coop_manager.app import create_app


@pytest.fixture
def app():
    """Create a fresh Flask app instance configured for testing."""
    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    """Return a test client for issuing requests without a running server."""
    return app.test_client()
