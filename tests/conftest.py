"""Fixtures that build a real podpack site with this app installed.

Testing the app in isolation would prove the views work and say nothing about
whether it is a well-formed app, which is the part that can break.
"""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from podpack import create_app

SiteFactory = Callable[..., Flask]

HOST_CONFIG: dict[str, Any] = {
    "site": {"name": "test site", "environment": "test", "apps": ["podpack_notes"]},
    "apps": {"notes": {"page_size": 5}},
}


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SiteFactory:
    """A podpack site with this app installed, roots pointed at tmp_path.

    Secrets come from the environment in production and `create_app` insists on
    them. The roots are real directories so the registry's per-app mkdir, data
    seeding and log wiring all run rather than being stubbed.
    """
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")

    def _build(**overrides: Any) -> Flask:
        config = {**HOST_CONFIG, **overrides.pop("host_config", {})}
        app = create_app(
            host_config=config,
            data_root=tmp_path / "data",
            log_root=tmp_path / "logs",
            **overrides,
        )
        with app.app_context():
            from podpack import db

            db.create_all()
        return app

    return _build


@pytest.fixture
def app(site: SiteFactory) -> Flask:
    return site()
