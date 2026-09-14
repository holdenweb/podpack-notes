"""Fixtures that build a real podpack site with this app installed.

Testing the app in isolation would prove the views work and say nothing about
whether it is a well-formed app, which is the part that can break.

Since a note has an owner, every fixture here also has to produce a *signed-in*
caller, and two of them: the claim this app now makes is that one user cannot see
another's notes, and a suite with one user cannot state it.
"""

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_security import hash_password
from sqlalchemy import event
from sqlalchemy.engine import Engine

from podpack import create_app

SiteFactory = Callable[..., Flask]

HOST_CONFIG: dict[str, Any] = {
    "site": {"name": "test site", "environment": "test", "apps": ["podpack_notes"]},
    "apps": {"notes": {"page_size": 5}},
}

OWNER = "owner@example.com"
STRANGER = "stranger@example.com"
PASSWORD = "test-password"


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    """Make SQLite behave like the database a site actually runs.

    SQLite parses a REFERENCES clause and then ignores it unless this pragma is
    set, per connection. Without it the `notes.owner_id` constraint exists in the
    schema and constrains nothing, so a test asserting that RESTRICT stops a user
    being deleted would pass whatever the model said -- and the one fact most
    worth knowing would be the one the suite could not report.

    Nothing in podpack or any sibling app does this yet; they have no foreign
    keys to enforce.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SiteFactory:
    """A podpack site with this app installed, roots pointed at tmp_path.

    Secrets come from the environment in production and `create_app` insists on
    them. The roots are real directories so the registry's per-app mkdir, data
    seeding and log wiring all run rather than being stubbed.
    """
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    # Required since podpack 0.5.2, when login became core: podpack refuses to
    # boot without it whether or not this app uses login. It does now.
    monkeypatch.setenv("SECURITY_PASSWORD_SALT", "test-password-salt")

    def _build(**overrides: Any) -> Flask:
        config = {**HOST_CONFIG, **overrides.pop("host_config", {})}
        app = create_app(
            {
                "TESTING": True,
                # Load-bearing: without it flask-security's login form rejects
                # the test client's POST for a missing CSRF token, and every
                # test here fails for a reason unrelated to what it asserts.
                "WTF_CSRF_ENABLED": False,
                # flask-security resolves MX records for the address it is
                # given, and example.com has none. Left on, `create_user` below
                # raises and the whole suite blames the wrong thing.
                "SECURITY_EMAIL_VALIDATOR_ARGS": {"check_deliverability": False},
            },
            host_config=config,
            data_root=tmp_path / "data",
            log_root=tmp_path / "logs",
            **overrides,
        )
        with app.app_context():
            from podpack import db

            db.create_all()
            _create_users()
        return app

    return _build


def _create_users() -> None:
    """Two ordinary users, through flask-security's own datastore.

    `hash_password` rather than a plaintext string: the column holds a hash, and
    a test that wrote a bare password would authenticate nobody.
    """
    from podpack import db
    from podpack.auth import user_datastore

    for email in (OWNER, STRANGER):
        user_datastore.create_user(
            email=email,
            password=hash_password(PASSWORD),
            active=True,
            # Harmless while SECURITY_CONFIRMABLE is off, and what keeps these
            # fixtures working on a site that turns it on.
            confirmed_at=datetime.now(timezone.utc),
        )
    db.session.commit()


def login(app: Flask, email: str = OWNER) -> FlaskClient:
    """A client holding a real session cookie, obtained the real way.

    Through flask-security's own `/login` form rather than by calling
    `login_user()` directly, so that what the tests exercise is the mechanism a
    browser uses and not our idea of it.

    The session is inspected rather than the status code, because a *failed*
    login also answers 200 -- it re-renders the form with an error. Asserting on
    the status would have accepted every broken login in this file.
    """
    client = app.test_client()
    client.post(
        "/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=True,
    )
    with client.session_transaction() as session:
        assert "_user_id" in session, f"logging in as {email} did not take"
    return client


@pytest.fixture
def app(site: SiteFactory) -> Flask:
    return site()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Signed in as OWNER, which is whose notes most of these tests are about."""
    return login(app)


@pytest.fixture
def stranger(app: Flask) -> FlaskClient:
    """Signed in as somebody else, on the same site as `client`."""
    return login(app, STRANGER)
