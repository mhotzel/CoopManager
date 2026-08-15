"""Tests for the application factory in coop_manager.app."""

from flask import Flask

from coop_manager.app import create_app


def test_create_app_returns_flask_instance():
    """create_app() should build a Flask application object."""
    app = create_app()
    assert isinstance(app, Flask)


def test_base_blueprint_is_registered():
    """The 'base' blueprint should be wired into the app."""
    app = create_app()
    assert "base" in app.blueprints
